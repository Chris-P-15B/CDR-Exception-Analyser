# CDR-Exception-Analyser
CUCM CDR/CMR Exception Analyser

(c) 2020, Chris Perkins

Licence: BSD 3-Clause



Parses CUCM CDR CSV files in a specified directory & picks out calls that have non-normal call termination cause codes between 2 UTC dates.

Parses CUCM CMR CSV files in a specified directory (if present) & picks out calls that have poor minimum MoS or maximum ICR between 2 UTC dates.

Outputs HTML reports that groups these calls by source or destination, to aid investigation & troubleshooting.

Inspired by AT&T Global Network Service's CDR Exception reporting process for customer CUCM deployments.

# Pre-Requisites:
* Python 3.6+
* Jinja2 module installed
* All CUCM nodes have CDR & optionally CMR enabled. Instructions: https://www.cisco.com/c/en/us/support/docs/unified-communications/unified-communications-manager-version-110/213526-configure-cdr-on-ccm-11-5.html
* If CMRs are enabled, don't forget to untick "Load CDR only"
* CUCM configured to export CDRs to FTP/SFTP server. Whilst it is possible to export CDRs from the CAR tool, the CMRs are in a different format & won't be parsed.

# Configuration
Two JSON files are used to store required configuration settings.
_exception_settings.json_ contains the thresholds & call termination causes that are considered OK. You will likely want to tweak the suggested defaults listed below to better match your environment.

```
{
	"cause_codes_excluded": ["0", "16", "17", "393216"],
	"cause_code_amber_threshold": 3,
	"cause_code_red_threshold": 5,
	"mos_threshold": 3.7,
	"icr_threshold": 0.02,
	"mos_amber_threshold": 3,
	"mos_red_threshold": 5
}
```

The default excluded cause codes are:
* 0 - No error
* 16 - Normal call clearing
* 17 - User busy
* 393216 - Call split (was 126) This code applies when a call terminates during a transfer operation because it was split off and terminated (was not part of the final transferred call). This code can help you to determine which calls terminated as part of a feature operation.

The amber & red thresholds are the number of CDR instances of a given call exception. Below the amber threshold is excluded from the report, over & above the red threshold is highlighted in the report.

The worst case MoS & ICR in CMRs is checked against the threshold (if present), if it is below the MoS threshold or above the ICR threshold, the CMR is considered an exception.
Explanation of CMR K-factor data: https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/service/11_5_1/cdrdef/cucm_b_cucm-cdr-administration-guide-1151/cucm_b_cucm-cdr-administration-guide-1151_chapter_01001.html

_termination_cause_codes.json_ contains the listing of termination cause codes & their descriptions, allowing these to be edited & new cause codes added. CUCM v11.5 cause codes documtation: https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/service/11_5_1/cdrdef/cucm_b_cucm-cdr-administration-guide-1151/cucm_b_cucm-cdr-administration-guide-1151_chapter_0110.html

# Usage
Command line parameters, for those with spaces enclose the parameter in "":

* Start date/time in %Y-%m-%d %H:%M:%S format
* End date/time in %Y-%m-%d %H:%M:%S format
* Input CSV files directory
* CDR report filename
* CMR report filename

For example:

_python CDR_exception_analyser.py "2020-04-01 00:00:00" "2020-04-10 23:59:59" "D:\CDR Files" output_cdr.html output_cmr.html_

It is suggested to run the tool to parse a week's worth of CDRs, as parsing large numbers of CDRs can be time consuming. For this reason, also avoid storing too many CDR files outside the date/time range in the input directory, as they will be inspected, but not parsed.

The output report provides a summary of information related to each CDR exception, to assist further investigation & troubleshooting.
