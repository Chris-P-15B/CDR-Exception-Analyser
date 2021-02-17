# CUCM CDR/CMR Exception Analyser

(c) 2020, Chris Perkins.


Parses CUCM CDR & CMR (if present) CSV files in a specified directory & picks out CDR exceptions between 2 UTC dates. A CDR exception being:
* For a given source device, all instances of a particular source cause code
* For a given source device, all instances of a particular destination cause code
* For a given destination device, all instances of a particular source cause code
* For a given destination device, all instances of a particular destination cause code
* For a given source device, all instances of poor MoS or CCR
* For a given destination device, all instances of poor MoS or CCR

Outputs HTML reports that groups these calls by source or destination, to aid investigation & troubleshooting.

Inspired by AT&T Global Network Service's CDR Exception reporting process for customer CUCM deployments.

* v1.4 - Code simplification & tidying.
* v1.3 - Added date/instance counts graph.
* v1.2 - Added table of contents to reports. Switched to MLQKav & CCR for call quality measure, as MLQKmn & ICRmx are worst case values & too sensitive to long calls with short periods of bad call quality.
* v1.1 - Fixed opening CDRs in a different directory, added device & cause code summary counts.
* v1.0 - Initial public release, bug fixes.
* v0.3 - Multiple file handling, completed CMR support & bug fixes.
* v0.2 - Added experimental CMR support & bug fixes.
* v0.1 - Initial development release, CDRs only.


# Pre-Requisites:
* Python 3.6+
* Jinja2 & Matplotlib packages installed
* All CUCM nodes have CDR & optionally CMR enabled. Instructions: https://www.cisco.com/c/en/us/support/docs/unified-communications/unified-communications-manager-version-110/213526-configure-cdr-on-ccm-11-5.html
* If CMRs are enabled, don't forget to untick "Load CDR only" in the CAR tool
* CUCM configured to export CDRs to FTP/SFTP server. Whilst it is possible to export CDRs from the CAR tool, the CMRs are in a different format & won't be parsed.

# Configuration
Two JSON files are used to store required configuration settings.
_exception_settings.json_ contains the thresholds & call termination causes that are considered OK. You will likely want to tweak the suggested defaults listed below to better match your environment.

```
{
	"cause_codes_excluded": ["0", "16", "17", "458752", "393216"],
	"cause_code_amber_threshold": 3,
	"cause_code_red_threshold": 5,
	"mos_threshold": 3.7,
	"ccr_threshold": 0.01,
	"mos_amber_threshold": 3,
	"mos_red_threshold": 5
}
```

The default excluded cause codes are:
* 0 - No error
* 16 - Normal call clearing
* 17 - User busy
* 458752 - Conference drop any party/Conference drop last party (was 128)
* 393216 - Call split (was 126) This code applies when a call terminates during a transfer operation because it was split off and terminated (was not part of the final transferred call). This code can help you to determine which calls terminated as part of a feature operation

The amber & red thresholds are the number of CDR instances of a given exception. Below the amber threshold is excluded from the report, over & above the red threshold is highlighted in the report.

If present, the average MoS & CCR in CMRs is checked against the thresholds, if it is below the MoS threshold or above the CCR threshold, the CMR is considered an exception.
Explanation of CMR K-factor data: https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/service/11_5_1/cdrdef/cucm_b_cucm-cdr-administration-guide-1151/cucm_b_cucm-cdr-administration-guide-1151_chapter_01001.html

_termination_cause_codes.json_ contains the listing of termination cause codes & their descriptions, allowing these to be edited & new cause codes added. CUCM termination cause codes documentation: https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/service/11_5_1/cdrdef/cucm_b_cucm-cdr-administration-guide-1151/cucm_b_cucm-cdr-administration-guide-1151_chapter_0110.html

# Usage
Command line parameters, for those with spaces enclose the parameter in "":

* Start date/time in %Y-%m-%d %H:%M:%S format, UTC timezone
* End date/time in %Y-%m-%d %H:%M:%S format, UTC timezone
* Input CSV files directory (must be CDRs from a single CUCM cluster)
* CDR report filename
* CMR report filename

For example:

_python CDR_exception_analyser.py "2020-04-01 00:00:00" "2020-04-10 23:59:59" "D:\CDR Files" output_cdr.html output_cmr.html_

It filters the files in the input file directory to only include those ending with ".csv". This behaviour is easily changed by editing the 2 lines that look like this:
```
filenames = (str(entry) for entry in basepath.glob("*.csv") if entry.is_file())
```

It is suggested to run the tool to parse a week's worth of CDRs, as parsing large numbers of CDRs can be time consuming. For this reason, also avoid storing too many CDR files outside the date/time range in the input directory, as they will be inspected but not parsed. Note that mixing CDRs from multiple CUCM clusters will confuse it, as the unique global call ID identifiers (callManagerId + globalCallID_callId) may overlap.

The report generated provides a summary & information related to each CDR exception, to assist further investigation & troubleshooting.
The summary section of the report lists how many exceptions were found that match the amber & red thresholds. Followed by a graph of all CDR instances with an excluded cause code or poor MoS/CCR by date. It then lists devices & cause codes ordered by count of instances with an excluded cause code or poor MoS/CCR. This includes instances that were below the threshold to be considered an exception.
The main section contains exceptions found, with the following fields from the CDRs (if present):

* callManagerId
* globalCallID_callId
* dateTimeOrigination
* origIpv4v6Addr
* destIpv4v6Addr
* callingPartyNumber
* originalCalledPartyNumber
* finalCalledPartyNumber
* origCause_value
* destCause_value
* origDeviceName
* destDeviceName
* origVarVQMetrics
* destVarVQMetrics
* duration
