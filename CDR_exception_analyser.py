#!/usr/bin/env python
# (c) 2020, Chris Perkins
# Licence: BSD 3-Clause

# Parses CUCM CDR CSV files & picks out calls that have non-normal cause codes between 2 UTC dates.
# Parses CUCM CMR CSV files & picks out calls that have poor average MoS or CCR between 2 UTC dates.
# Outputs HTML reports that groups these calls by source or destination, to aid investigation & troubleshooting.
# Inspired by AT&T Global Network Service's CDR Exception reporting process for customer CUCM deployments.

# v1.2 - Added table of contents to reports. Switched to MLQKav & CCR for call quality measure, as
# MLQKmn & ICRmx are worst case values & too sensitive to long calls with short periods of bad call quality.
# v1.1 - Fixed opening CDRs in a different directory, added device & cause code summary counts
# v1.0 - Initial public release, bug fixes.
# v0.3 - Multiple file handling, completed CMR support & bug fixes.
# v0.2 - Added experimental CMR support & bug fixes.
# v0.1 - initial development release, CDRs only.

import csv, sys, json, itertools, re, operator
from datetime import datetime
from jinja2 import Template, Environment, FileSystemLoader
from pathlib import Path
from collections import OrderedDict

# Stores required information for a single CDR/CMR
class CDRInstance:
    def __init__(self, **kwargs):
        """Parameters:
        cdr_record_type - integer (1 CDR, 2 CMR)
        global_callmanager_id - string
        global_call_id - string
        date_time_origination - datetime
        orig_ipv4v6_addr - string
        dest_ipv4v6_addr - string
        calling_party_number - string
        original_called_party_number - string
        final_called_party_number - string
        orig_cause_value - string
        dest_cause_value - string
        orig_device_name - string
        dest_device_name - string
        duration - string
        orig_vq_metrics - string
        dest_vq_metrics - string
        """
        self.cdr_record_type = kwargs.get("cdr_record_type", None)
        assert self.cdr_record_type is not None
        # Sanity checks, CDRs
        if self.cdr_record_type == 1:
            self.global_callmanager_id = kwargs.get("global_callmanager_id", None)
            self.global_call_id = kwargs.get("global_call_id", None)
            self.date_time_origination = kwargs.get("date_time_origination", None)
            self.orig_ipv4v6_addr = kwargs.get("orig_ipv4v6_addr", None)
            self.dest_ipv4v6_addr = kwargs.get("dest_ipv4v6_addr", None)
            self.calling_party_number = kwargs.get("calling_party_number", None)
            self.original_called_party_number = kwargs.get("original_called_party_number", None)
            self.final_called_party_number = kwargs.get("final_called_party_number", None)
            self.orig_cause_value = kwargs.get("orig_cause_value", None)
            self.dest_cause_value = kwargs.get("dest_cause_value", None)
            self.orig_device_name = kwargs.get("orig_device_name", None)
            self.dest_device_name = kwargs.get("dest_device_name", None)
            self.duration = kwargs.get("duration", None)
            assert self.global_callmanager_id is not None
            assert self.global_call_id is not None
            assert self.date_time_origination is not None
            assert self.orig_ipv4v6_addr is not None
            assert self.dest_ipv4v6_addr is not None
            assert self.calling_party_number is not None
            assert self.original_called_party_number is not None
            assert self.final_called_party_number is not None
            assert self.orig_cause_value is not None
            assert self.dest_cause_value is not None
            assert self.orig_device_name is not None
            assert self.dest_device_name is not None
            assert self.duration is not None
        # CMRs
        elif self.cdr_record_type == 2:
            self.global_callmanager_id = kwargs.get("global_callmanager_id", None)
            self.global_call_id = kwargs.get("global_call_id", None)
            self.date_time_origination = kwargs.get("date_time_origination", None)
            self.calling_party_number = kwargs.get("calling_party_number", None)
            self.original_called_party_number = kwargs.get("original_called_party_number", None)
            self.final_called_party_number = kwargs.get("final_called_party_number", None)
            self.orig_device_name = kwargs.get("orig_device_name", None)
            self.dest_device_name = kwargs.get("dest_device_name", None)
            self.orig_vq_metrics = kwargs.get("orig_vq_metrics", None)
            self.dest_vq_metrics = kwargs.get("dest_vq_metrics", None)
            self.orig_ipv4v6_addr = kwargs.get("orig_ipv4v6_addr", None)
            self.dest_ipv4v6_addr = kwargs.get("dest_ipv4v6_addr", None)
            self.duration = kwargs.get("duration", None)
            assert self.global_callmanager_id is not None
            assert self.global_call_id is not None
            assert self.date_time_origination is not None
            assert self.calling_party_number is not None
            assert self.original_called_party_number is not None
            assert self.final_called_party_number is not None
            assert self.orig_device_name is not None
            assert self.dest_device_name is not None
            assert self.orig_vq_metrics is not None or self.dest_vq_metrics is not None
            assert self.orig_ipv4v6_addr is not None
            assert self.dest_ipv4v6_addr is not None
            assert self.duration is not None

    def __str__(self):
        """String respresentation of a CDRInstance"""
        # CDRs
        if self.cdr_record_type == 1:
            return f"{self.cdr_record_type}, {self.global_callmanager_id}, {self.global_call_id}, " \
                f"{self.date_time_origination.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_ipv4v6_addr}, {self.dest_ipv4v6_addr}, " \
                f"{self.calling_party_number}, {self.original_called_party_number}, {self.final_called_party_number}, " \
                f"{self.orig_cause_value}, {self.dest_cause_value}, {self.orig_device_name}, {self.dest_device_name}, {self.duration}"
        # CMRs
        elif self.cdr_record_type == 2:
            return f"{self.cdr_record_type}, {self.global_callmanager_id}, {self.global_call_id}, " \
                f"{self.date_time_origination.strftime('%Y-%m-%d %H:%M:%S')}, {self.orig_ipv4v6_addr}, {self.dest_ipv4v6_addr}, " \
                f"{self.calling_party_number}, {self.original_called_party_number}, {self.final_called_party_number}, " \
                f"{self.orig_device_name}, {self.dest_device_name}, {self.orig_vq_metrics}, {self.dest_vq_metrics}, {self.duration}"

# Stores a list of CDRInstances for a given exception, an exception being:
# For a given source device, all instances of a particular source cause code
# For a given source device, all instances of a particular destination cause code
# For a given destination device, all instances of a particular source cause code
# For a given destination device, all instances of a particular destination cause code
# For a given source device, all instances of poor MoS or CCR
# For a given destination device, all instances of poor MoS or CCR
class CDRException:
    def __init__(self, **kwargs):
        """Parameters, orig or dest required:
        orig_cause_value - string
        dest_cause_value - string
        orig_device_name - string
        dest_device_name - string
        cdr_instance - CDRInstance
        cause_codes - dictionary
        """
        self.orig_cause_value = kwargs.get("orig_cause_value", None)
        self.dest_cause_value = kwargs.get("dest_cause_value", None)
        self.orig_device_name = kwargs.get("orig_device_name", None)
        self.dest_device_name = kwargs.get("dest_device_name", None)
        self.cdr_instances = [kwargs.get("cdr_instance", None)]

        # Sanity checks
        assert self.cdr_instances[0] is not None
        self.cdr_record_type = self.cdr_instances[0].cdr_record_type
        assert self.orig_device_name is not None or self.dest_device_name is not None
        if self.cdr_record_type == 1:
            assert self.orig_cause_value is not None or self.dest_cause_value is not None

def load_config():
    """Loads configuration information from JSON files.
    Returns:
    configuration settings - dictionary
    cause codes - dictionary"""
    try:
        with open("exception_settings.json") as f:
            config_settings = json.load(f)
    except json.JSONDecodeError:
        print("Error: Unable to parse exception_settings.json")
        sys.exit()
    except FileNotFoundError:
        print("Error: Unable to open exception_settings.json")
        sys.exit()
    # Sanity checks
    if config_settings.get("cause_codes_excluded", None) is None:
        print("Error: Excluded cause codes missing")
        sys.exit()
    if config_settings.get("cause_code_amber_threshold", None) is None:
        print("Error: Cause code amber threshold missing")
        sys.exit()
    if config_settings.get("cause_code_red_threshold", None) is None:
        print("Error: Cause code red threshold missing")
        sys.exit()
    if config_settings.get("mos_threshold", None) is None:
        print("Error: MoS threshold missing")
        sys.exit()
    if config_settings.get("ccr_threshold", None) is None:
        print("Error: CCR threshold missing")
        sys.exit()
    if config_settings.get("mos_amber_threshold", None) is None:
        print("Error: MoS amber threshold missing")
        sys.exit()
    if config_settings.get("mos_red_threshold", None) is None:
        print("Error: MoS red threshold missing")
        sys.exit()
    try:
        config_settings["cause_code_amber_threshold"] = int(config_settings["cause_code_amber_threshold"])
        config_settings["cause_code_red_threshold"] = int(config_settings["cause_code_red_threshold"])
        config_settings["mos_threshold"] = float(config_settings["mos_threshold"])
        config_settings["ccr_threshold"] = float(config_settings["ccr_threshold"])
        config_settings["mos_amber_threshold"] = int(config_settings["mos_amber_threshold"])
        config_settings["mos_red_threshold"] = int(config_settings["mos_red_threshold"])
    except TypeError:
        print("Error: One or more numeric thresholds is not a valid number")
        sys.exit()

    try:
        with open("termination_cause_codes.json") as f:
            cause_codes = json.load(f)
    except json.JSONDecodeError:
        print("Error: Unable to parse termination_cause_codes.json")
        sys.exit()
    except FileNotFoundError:
        print("Error: Unable to open termination_cause_codes.json")
        sys.exit()
    # Sanity checks
    if len(cause_codes) == 0:
        print("Error: Unable to load termination cause codes")
        sys.exit()
    return config_settings, cause_codes

def load_cdrs(filepath, config_settings, start_date, end_date):
    """Load CDRs from the specified file, storing those within the date/time range.
    Parameters:
    filepath - string
    config_settings - dictionary
    start_date - datetime
    end_date - datetime

    Returns:
    cdr_list - list of CDRInstance"""
    # Retrieve list of .csv files
    basepath = Path(filepath)
    filenames = (str(entry) for entry in basepath.iterdir() if entry.is_file() and ".csv" in entry.name)
    cdr_list = []
    for filename in filenames:
        try:
            columns = {}
            # encoding="utf-8-sig" is necessary for correct parsing of UTF-8 encoding of CUCM CDR CSV files
            with open(filename, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header_row = next(reader)
                # Locate columns of interest & store index in dictionary
                cntr = 0
                for index, column_header in enumerate(header_row):
                    column_header = column_header.lower()
                    if column_header == "cdrrecordtype":
                        columns["cdrRecordType"] = index
                        cntr += 1
                    elif column_header == "globalcallid_callmanagerid":
                        columns["globalCallID_callManagerId"] = index
                        cntr += 1
                    elif column_header == "globalcallid_callid":
                        columns["globalCallID_callId"] = index
                        cntr += 1
                    elif column_header == "datetimeorigination":
                        columns["dateTimeOrigination"] = index
                        cntr += 1
                    elif column_header == "origipv4v6addr":
                        columns["origIpv4v6Addr"] = index
                        cntr += 1
                    elif column_header == "destipv4v6addr":
                        columns["destIpv4v6Addr"] = index
                        cntr += 1
                    elif column_header == "callingpartynumber":
                        columns["callingPartyNumber"] = index
                        cntr += 1
                    elif column_header == "originalcalledpartynumber":
                        columns["originalCalledPartyNumber"] = index
                        cntr += 1
                    elif column_header == "finalcalledpartynumber":
                        columns["finalCalledPartyNumber"] = index
                        cntr += 1
                    elif column_header == "origcause_value":
                        columns["origCause_value"] = index
                        cntr += 1
                    elif column_header == "destcause_value":
                        columns["destCause_value"] = index
                        cntr += 1
                    elif column_header == "origdevicename":
                        columns["origDeviceName"] = index
                        cntr += 1
                    elif column_header == "destdevicename":
                        columns["destDeviceName"] = index
                        cntr += 1
                    elif column_header == "duration":
                        columns["duration"] = index
                        cntr += 1
                if cntr == 14:
                    print(f"Loading CDR file: {filename}")
                else:
                    # Skip to next file
                    continue

                # Read CDR entries & store in list of CDRInstance
                for row in reader:
                    fields = {}
                    try:
                        fields["cdr_record_type"] = 1
                        fields["global_callmanager_id"] = row[columns["globalCallID_callManagerId"]]
                        fields["global_call_id"] = row[columns["globalCallID_callId"]]
                        fields["date_time_origination"] = datetime.fromtimestamp(int(row[columns["dateTimeOrigination"]]))
                        fields["orig_ipv4v6_addr"] = row[columns["origIpv4v6Addr"]]
                        fields["dest_ipv4v6_addr"] = row[columns["destIpv4v6Addr"]]
                        fields["calling_party_number"] = row[columns["callingPartyNumber"]]
                        fields["original_called_party_number"] = row[columns["originalCalledPartyNumber"]]
                        fields["final_called_party_number"] = row[columns["finalCalledPartyNumber"]]
                        fields["orig_cause_value"] = row[columns["origCause_value"]]
                        fields["dest_cause_value"] = row[columns["destCause_value"]]
                        fields["orig_device_name"] = row[columns["origDeviceName"]]
                        fields["dest_device_name"] = row[columns["destDeviceName"]]
                        fields["duration"] = row[columns["duration"]]

                        # Date/time check
                        if fields["date_time_origination"] >= start_date and fields["date_time_origination"] <= end_date:
                            cdr_list.append(CDRInstance(**fields))
                    except (TypeError, ValueError):
                        print(f"Error: Unable to parse {filename}, row: {fields}")
                        # Skip to next row
                        continue
        except (IOError, csv.Error):
            print(f"Error: Unable to load CDR file: {filename}")
            # Skip to next file
            continue
    print(f"Loaded {len(cdr_list)} CDR records")
    return cdr_list

def load_cmrs(filepath, cdr_list, config_settings, start_date, end_date):
    """Load CMRs from the specified file, storing those within the date/time range where MoS/CCR is worse than the thresholds.
    Parameters:
    filepath - string
    cdr_list - list of CDRInstance
    config_settings - dictionary
    start_date - datetime
    end_date - datetime

    Returns:
    cmr_list - list of CDRInstance"""
    # Retrieve list of .csv files
    basepath = Path(filepath)
    filenames = (str(entry) for entry in basepath.iterdir() if entry.is_file() and ".csv" in entry.name)
    cmr_list = []
    for filename in filenames:
        try:
            columns = {}
            # encoding="utf-8-sig" is necessary for correct parsing of UTF-8 encoding of CUCM CMR CSV files
            with open(filename, encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header_row = next(reader)
                # Locate columns of interest & store index in dictionary
                cntr = 0
                for index, column_header in enumerate(header_row):
                    column_header = column_header.lower()
                    if column_header == "cdrrecordtype":
                        columns["cdrRecordType"] = index
                        cntr += 1
                    elif column_header == "globalcallid_callmanagerid":
                        columns["globalCallID_callManagerId"] = index
                        cntr += 1
                    elif column_header == "globalcallid_callid":
                        columns["globalCallID_callId"] = index
                        cntr += 1
                    elif column_header == "datetimestamp":
                        columns["dateTimeOrigination"] = index
                        cntr += 1
                    elif column_header == "devicename":
                        columns["deviceName"] = index
                        cntr += 1
                    elif column_header == "varvqmetrics":
                        columns["varVQMetrics"] = index
                        cntr += 1
                    elif column_header == "duration":
                        columns["duration"] = index
                        cntr += 1
                if cntr == 7:
                    print(f"Loading CMR file: {filename}")
                else:
                    # Skip to next file
                    continue

                # Read CMR entries & store in list of CDRInstance
                for row in reader:
                    fields = {}
                    try:
                        fields["cdr_record_type"] = 2
                        fields["global_callmanager_id"] = row[columns["globalCallID_callManagerId"]]
                        fields["global_call_id"] = row[columns["globalCallID_callId"]]
                        fields["date_time_origination"] = datetime.fromtimestamp(int(row[columns["dateTimeOrigination"]]))
                        # Date/time check
                        if fields["date_time_origination"] < start_date or fields["date_time_origination"] > end_date:
                            continue
                        # MLQK average or CCR check
                        mlqk_str = re.search(r"MLQKav=([\d\.]+);", row[columns["varVQMetrics"]])
                        if mlqk_str:
                            mlqk = float(mlqk_str.group(1))
                            if mlqk >= config_settings["mos_threshold"]:
                                continue
                        ccr_str = re.search(r"CCR=([\d\.]+);", row[columns["varVQMetrics"]])
                        if ccr_str:
                            ccr = float(ccr_str.group(1))
                            if ccr <= config_settings["ccr_threshold"]:
                                continue
                        # No MoS or CCR found, skip
                        if not mlqk_str and not ccr_str:
                            continue

                        # Find matching CDR to extract additional fields
                        found = 0
                        for cdr in cdr_list:
                            if (cdr.global_callmanager_id == fields["global_callmanager_id"] and
                                cdr.global_call_id == fields["global_call_id"]):
                                # CDR fields
                                fields["orig_ipv4v6_addr"] = cdr.orig_ipv4v6_addr
                                fields["dest_ipv4v6_addr"] = cdr.dest_ipv4v6_addr
                                fields["calling_party_number"] = cdr.calling_party_number
                                fields["original_called_party_number"] = cdr.original_called_party_number
                                fields["final_called_party_number"] = cdr.final_called_party_number
                                # CMR fields, matching against CDR to identify as orig or dest device
                                fields["duration"] = row[columns["duration"]]
                                if row[columns["deviceName"]] == cdr.orig_device_name:
                                    fields["orig_device_name"] = row[columns["deviceName"]]
                                    fields["dest_device_name"] = cdr.dest_device_name
                                    fields["orig_vq_metrics"] = row[columns["varVQMetrics"]]
                                elif row[columns["deviceName"]] == cdr.dest_device_name:
                                    fields["dest_device_name"] = row[columns["deviceName"]]
                                    fields["orig_device_name"] = cdr.orig_device_name
                                    fields["dest_vq_metrics"] = row[columns["varVQMetrics"]]
                                # Transferred calls the global call ID can match more than one CDR with different
                                # device names, so keep searching
                                else:
                                    found = 1
                                    continue
                                # Otherwise matched a CDR, so no further searching required
                                cmr_list.append(CDRInstance(**fields))
                                found = 2
                                break

                        # Catch if global call ID matched, but device name didn't match
                        if found == 1:
                            fields["orig_device_name"] = row[columns["deviceName"]]
                            fields["dest_device_name"] = row[columns["deviceName"]]
                            fields["orig_vq_metrics"] = row[columns["varVQMetrics"]]
                            fields["dest_vq_metrics"] = row[columns["varVQMetrics"]]
                            cmr_list.append(CDRInstance(**fields))
                    except (TypeError, ValueError):
                        print(f"Error: Unable to parse {filename}, row: {fields}")
                        # Skip to next row
                        continue
        except (IOError, csv.Error):
            print(f"Error: Unable to load CMR file: {filename}")
            # Skip to next file
            continue
    return cmr_list

def parse_cdrs(cdr_list, config_settings):
    """Parse list of CDRInstance to generate & return list of CDRException for CDRInstances where termination
    cause code isn't in the list of exclusions or MoS/CCR is worse than the thresholds.
    Parameters:
    cdr_list - list of CDRIstance
    config settings - dictionary

    Returns:
    cdr_exceptions - list of CDRException
    devices_cntr - OrderedDict
    causes_cntr - OrderedDict"""
    # Filter CDRInstance before parsing
    if len(cdr_list) > 0:
        # For CDRs remove CDRInstance with excluded termination cause codes
        if cdr_list[0].cdr_record_type == 1:
            cdr_list = [cdr for cdr in cdr_list if cdr.orig_cause_value not in config_settings["cause_codes_excluded"] or
                cdr.dest_cause_value not in config_settings["cause_codes_excluded"]]
            print(f"Parsed {len(cdr_list)} CDR records")
        elif cdr_list[0].cdr_record_type == 2:
            print(f"Parsed {len(cdr_list)} CMR records")
    # Extract deduplicated list of devices & causes from CDRInstances, count totals for devices & cause codes in CDRInstances
    devices = []
    causes = ["-1"] # Kludge to ensure CMRs get iterated by "for device, cause in" loop
    devices_cntr = {}
    causes_cntr = {}
    for cdr in cdr_list:
        # Exclude blank device name, no device means no valid cause code or MoS/CCR
        if cdr.orig_device_name != "" and cdr.orig_device_name not in devices:
            devices.append(cdr.orig_device_name)
            devices_cntr[cdr.orig_device_name] = 0
        if cdr.dest_device_name != "" and cdr.dest_device_name not in devices:
            devices.append(cdr.dest_device_name)
            devices_cntr[cdr.dest_device_name] = 0
        # CDRs
        if cdr.cdr_record_type == 1:
            if cdr.orig_cause_value not in causes:
                causes.append(cdr.orig_cause_value)
                if cdr.orig_cause_value not in config_settings["cause_codes_excluded"]:
                    causes_cntr[cdr.orig_cause_value] = 0
            if cdr.dest_cause_value not in causes:
                causes.append(cdr.dest_cause_value)
                if cdr.dest_cause_value not in config_settings["cause_codes_excluded"]:
                    causes_cntr[cdr.dest_cause_value] = 0

    # Find exceptions & track counts by device & cause
    cdr_exceptions = []
    for device, cause in itertools.product(devices, causes):
        for cdr in cdr_list:
            # CDRs
            if cdr.cdr_record_type == 1:
                # For a given source device, all instances of a particular source cause code
                if (device == cdr.orig_device_name and cause == cdr.orig_cause_value and
                    cdr.orig_cause_value not in config_settings["cause_codes_excluded"]):
                    found = find_cdr_exception(cdr_exceptions, orig_device_name=device, orig_cause_value=cause)
                    if found is None:
                        cdr_exceptions.append(CDRException(orig_device_name=device, orig_cause_value=cause, cdr_instance=cdr))
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1

                # For a given source device, all instances of a particular destination cause code
                if (device == cdr.orig_device_name and cause == cdr.dest_cause_value and
                    cdr.dest_cause_value not in config_settings["cause_codes_excluded"]):
                    found = find_cdr_exception(cdr_exceptions, orig_device_name=device, dest_cause_value=cause)
                    if found is None:
                        cdr_exceptions.append(CDRException(orig_device_name=device, dest_cause_value=cause, cdr_instance=cdr))
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1

                # For a given destination device, all instances of a particular source cause code
                if (device == cdr.dest_device_name and cause == cdr.orig_cause_value and
                    cdr.orig_cause_value not in config_settings["cause_codes_excluded"]):
                    found = find_cdr_exception(cdr_exceptions, dest_device_name=device, orig_cause_value=cause)
                    if found is None:
                        cdr_exceptions.append(CDRException(dest_device_name=device, orig_cause_value=cause, cdr_instance=cdr))
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1

                # For a given destination device, all instances of a particular destination cause code
                if (device == cdr.dest_device_name and cause == cdr.dest_cause_value and
                    cdr.dest_cause_value not in config_settings["cause_codes_excluded"]):
                    found = find_cdr_exception(cdr_exceptions, dest_device_name=device, dest_cause_value=cause)
                    if found is None:
                        cdr_exceptions.append(CDRException(dest_device_name=device, dest_cause_value=cause, cdr_instance=cdr))
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1
                        causes_cntr[cause] += 1
            # CMRs
            elif cdr.cdr_record_type == 2:
                # For a given source device, all instances of poor MoS or CCR
                if device == cdr.orig_device_name:
                    found = find_cdr_exception(cdr_exceptions, orig_device_name=device)
                    if found is None:
                        cdr_exceptions.append(CDRException(orig_device_name=device, cdr_instance=cdr))
                        devices_cntr[device] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1

                # For a given destination device, all instances of poor MoS or CCR
                if device == cdr.dest_device_name:
                    found = find_cdr_exception(cdr_exceptions, dest_device_name=device)
                    if found is None:
                        cdr_exceptions.append(CDRException(dest_device_name=device, cdr_instance=cdr))
                        devices_cntr[device] += 1
                    else:
                        found.cdr_instances.append(cdr)
                        devices_cntr[device] += 1

    # Sort device & cause code counts in descending order
    devices_cntr = OrderedDict(sorted(devices_cntr.items(), key=operator.itemgetter(1), reverse=True))
    causes_cntr = OrderedDict(sorted(causes_cntr.items(), key=operator.itemgetter(1), reverse=True))
    return cdr_exceptions, devices_cntr, causes_cntr

def find_cdr_exception(cdr_exceptions, orig_device_name=None, dest_device_name=None, orig_cause_value=None, dest_cause_value=None):
    """For given list of CDRException, find & return first CDRException for given device & cause (optional), else return None.
    Parameters, orig or dest required (CMRs device only):
    cdr_exceptions - list of CDRException
    orig_device_name - string
    dest_device_name - string
    orig_cause_value - string
    dest_cause_value - string

    Returns:
    cdr_exception - CDRException"""
    # Sanity checks
    assert orig_device_name is not None or dest_device_name is not None
    if len(cdr_exceptions) > 0:
        if cdr_exceptions[0].cdr_instances[0].cdr_record_type == 1:
            assert orig_cause_value is not None or dest_cause_value is not None
    # Iterate through CDRExceptions to find a match
    for cdr_exception in cdr_exceptions:
        # CDRs
        if cdr_exception.cdr_record_type == 1:
            if orig_device_name is not None:
                if orig_cause_value is not None:
                    if orig_cause_value == cdr_exception.orig_cause_value and orig_device_name == cdr_exception.orig_device_name:
                        return cdr_exception
                elif dest_cause_value is not None:
                    if dest_cause_value == cdr_exception.dest_cause_value and orig_device_name == cdr_exception.orig_device_name:
                        return cdr_exception
            if dest_device_name is not None:
                if orig_cause_value is not None:
                    if orig_cause_value == cdr_exception.orig_cause_value and dest_device_name == cdr_exception.dest_device_name:
                        return cdr_exception
                elif dest_cause_value is not None:
                    if dest_cause_value == cdr_exception.dest_cause_value and dest_device_name == cdr_exception.dest_device_name:
                        return cdr_exception
        # CMRs
        elif cdr_exception.cdr_record_type == 2:
            if orig_device_name is not None:
                if cdr_exception.orig_device_name is not None and orig_device_name == cdr_exception.orig_device_name:
                    return cdr_exception
            if dest_device_name is not None:
                if cdr_exception.dest_device_name is not None and dest_device_name == cdr_exception.dest_device_name:
                    return cdr_exception
    # No match?
    return None

def generate_report(cdr_exceptions, devices_cntr, causes_cntr, config_settings, cause_codes, start_date, end_date, filename):
    """For given list of CDRException, config parameters & cause codes, generate HTML report.
    Parameters:
    cdr_exceptions - list of CDRException
    devices_cntr - OrderedDict
    causes_cntr - OrderedDict
    config_settings - dictionary
    cause_codes - dictionary
    start_date - datetime
    end_date - datetime
    filename - string"""
    file_loader = FileSystemLoader(".")
    env = Environment(loader=file_loader)
    if len(cdr_exceptions) > 0:
        amber_count = 0
        red_count = 0
        filtered_list = []
        if cdr_exceptions[0].cdr_instances[0].cdr_record_type == 1:
            template = env.get_template("cdr_exception_report.j2")
            # Exclude CDRException below the amber threshold
            for cdr_exception in cdr_exceptions:
                if len(cdr_exception.cdr_instances) >= config_settings["cause_code_red_threshold"]:
                    red_count += 1
                    filtered_list.append(cdr_exception)
                elif len(cdr_exception.cdr_instances) >= config_settings["cause_code_amber_threshold"]:
                    amber_count += 1
                    filtered_list.append(cdr_exception)
            print(f"{len(filtered_list)} CDR exceptions found")
        elif cdr_exceptions[0].cdr_instances[0].cdr_record_type == 2:
            template = env.get_template("cmr_exception_report.j2")
            # Exclude CDRException below the amber threshold
            for cdr_exception in cdr_exceptions:
                if len(cdr_exception.cdr_instances) >= config_settings["mos_red_threshold"]:
                    red_count += 1
                    filtered_list.append(cdr_exception)
                elif len(cdr_exception.cdr_instances) >= config_settings["mos_amber_threshold"]:
                    amber_count += 1
                    filtered_list.append(cdr_exception)
            print(f"{len(filtered_list)} CMR exceptions found")
        try:
            with open(filename, "w") as f:
                f.write(template.render(cdr_exceptions=filtered_list, devices_cntr=devices_cntr, causes_cntr=causes_cntr,
                    cause_codes=cause_codes, config_settings=config_settings, amber_count=amber_count, red_count=red_count,
                    start_date=start_date, end_date=end_date))
        except IOError:
            print(f"Error: Unable to write file {filename}")
    else:
        print("No CDR/CMR exceptions found")

def main():
    """Parse command line parameters & handle accordingly"""
    print("")
    if len(sys.argv) != 6:
        print(f"Usage {sys.argv[0]} [start date/time %Y-%m-%d %H:%M:%S] [end date/time %Y-%m-%d %H:%M:%S]"
            " [input files directory] [CDR report filename] [CMR report filename]")
        sys.exit()
    try:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d %H:%M:%S")
        end_date = datetime.strptime(sys.argv[2], "%Y-%m-%d %H:%M:%S")
        cdr_filepath = sys.argv[3]
        cdr_report = sys.argv[4]
        cmr_report = sys.argv[5]
    except ValueError:
        print("Error: Incorrectly formatted date/time")
        sys.exit()

    config_settings, cause_codes = load_config()
    cdr_list = load_cdrs(cdr_filepath, config_settings, start_date, end_date)
    cmr_list = load_cmrs(cdr_filepath, cdr_list, config_settings, start_date, end_date)
    cdr_exceptions, cdr_devices_cntr, cdr_causes_cntr = parse_cdrs(cdr_list, config_settings)
    cmr_exceptions, cmr_devices_cntr, cmr_causes_cntr = parse_cdrs(cmr_list, config_settings)
    generate_report(cdr_exceptions, cdr_devices_cntr, cdr_causes_cntr, config_settings, cause_codes,
        start_date, end_date, cdr_report)
    generate_report(cmr_exceptions, cmr_devices_cntr, cmr_causes_cntr, config_settings, cause_codes,
        start_date, end_date, cmr_report)

if __name__ == "__main__":
    main()