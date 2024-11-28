#!/usr/bin/env python3

import argparse
import pathlib
import fnmatch
import json
import re

s_pattern = '\n'

def format_android_info(info):
    info_struct = {}
    extracted = info.split(";", 1)
    timestamp = extracted[0]
    url = extracted[1]
    url = url.split(":", 4)[4].strip()
    status_regex = re.compile(" - ([0-9]{3})")
    status = status_regex.findall(url)
    status_code = status[0]
    info_struct["timestamp"] = timestamp
    info_struct["status"] = status_code
    info_struct["other"] = url
    return info_struct

def extract_android_properties(block):
    block_dict = {}
    for line in block:
        header = line.split(":", 1)
        if len(header) == 2:
            block_dict[header[0]] = header[1]
    return block_dict

def process_android_request(block):
    request_dict = {}
    body_index = len(block)
    body_regex = re.compile("^[\{\"]")
    for i, line in enumerate(block):
        if body_regex.search(line):
            body_index = i
            break
    request_dict["headers"] = extract_android_properties(block[0:body_index])
    if body_index != len(block):
        body = ("".join(block[body_index:])).strip(s_pattern)
    else:
        body = None
    request_dict["body"] = body
    return request_dict
 
def process_android_block(block):
    block_dict = {}
    req_index = None
    resp_index = None
    info = format_android_info(block[0].strip(s_pattern))
    block_dict["info"] = info
    block_dict["request"] = None
    block_dict["response"] = None
    if len(block) > 1:
        for i, line in enumerate(block):
            if "===== Request =====" in line:
                req_index = i        
            if "===== Response =====" in line:
                resp_index = i
        request = block[req_index:resp_index - 1]
        response = block[resp_index:]
        block_dict["request"] = process_android_request(request)
        block_dict["response"]  = process_android_request(response)
    return block_dict

def print_android_entry(block, args):
    print(f'{block["info"]["timestamp"]}: {block["info"]["other"]}')
    if args.req:
        if block["request"] is not None:
            print(f'->\n{block["request"]}')
        else:
            print('->')
    if args.resp:
        if block["response"] is not None:
            print(f'<-\n {block["response"]["body"]}')
        else:
            print('<-')

def print_android_requests(args, filepath, os):
    request_line = re.compile("Info\: HTTP [0-9]{1,} <-")
    with open(filepath) as file:
        block = list()
        for line in file:
            if len(block) > 0:
                if line.startswith("<-- END HTTP"):
                    print_block(block, args, os)
                    block.clear()
                else:
                    block.append(line)
            if request_line.search(line):
                block.clear()
                block.append(line)

def extract_ios_properties(block):
    block_dict = {}
    for i, line in enumerate(block):
        if line.startswith("["):
            key = line.strip(s_pattern)[1:-1].lower()
            block_dict[key] = block[i + 1].strip(s_pattern).lower()
    return block_dict

def process_ios_request(block):
    request_dict = {}
    headers_index = None
    body_index = None
    for i, line in enumerate(block):
        if line.startswith("### Headers"): headers_index = i
        if line.startswith("### Body"): body_index = i
    request_dict["headers"] = extract_ios_properties(block[headers_index:body_index])
    body = ("".join(block[body_index + 2:])).strip(s_pattern)
    if "Request body is empty" in body:
        request_dict["body"] = ""
    else:
        request_dict["body"] = body
    return request_dict
 
def process_ios_block(block):
    block_dict = {}
    req_index = None
    resp_index = None
    for i, line in enumerate(block):
        if line.startswith("## REQUEST"):
            req_index = i        
        if line.startswith("## RESPONSE"):
            resp_index = i
    info = block[0:req_index - 1]
    request = block[req_index:resp_index - 1]
    response = block[resp_index:]
    block_dict["info"] = extract_ios_properties(info)
    block_dict["request"] = process_ios_request(request)
    block_dict["response"]  = process_ios_request(response)
    if block_dict.get("info", {}).get("status") is None:
        block_dict["info"]["status"] = 0
    return block_dict

def print_ios_entry(block, args):
    print(f'{block["info"]["request date"]}: {block["info"]["method"]}:{block["info"]["status"]} {block["info"]["url"]}')
    if args.req:
        if len(block["request"]["body"]) > 0:
            print(f'->\n{block["request"]["body"]}')
        else:
            print('->')
    if args.resp:
        if len(block["response"]["body"]) > 0:
            print(f'<-\n {block["response"]["body"]}')
        else:
            print('<-')

def print_ios_requests(args, filepath, os):
    with open(filepath) as file:
        block = list()
        for line in file:
            if line.startswith("## INFO"):
                block.clear()
                block.append(line)
            if line.startswith("------------------------------"):
                print_block(block, args, os)
            if len(block) > 0:
                block.append(line)

def print_block(block, args, os):
    block_dict = process_block(block, os)
    if args.res_ok:
        if int(block_dict["info"]["status"]) < 400:
            apply_filter(args, block_dict, os)
    elif args.res_nok:
        if int(block_dict["info"]["status"]) >= 400:
            apply_filter(args, block_dict, os)
    else:
        apply_filter(args, block_dict, os)

def process_block(block, os):
    if os == "ios":
        return process_ios_block(block)
    if os == "android":
        return process_android_block(block)

def print_entry(block_dict, args, os):
    if os == "ios":
        print_ios_entry(block_dict, args)
    if os == "android":
        print_android_entry(block_dict, args)

def apply_filter(args, block_dict, os):
    if args.filter:
        text = json.dumps(block_dict)
        if fnmatch.fnmatch(text, args.filter):
            print_entry(block_dict, args, os)
    else:
        print_entry(block_dict, args, os)

def main():
    os = None
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Path to ios logfile")
    parser.add_argument("--req", help="Include request", action='store_true')
    parser.add_argument("--resp", help="Include response", action='store_true')
    parser.add_argument("--filter", help="String to filter blocks")
    parser.add_argument("--res-ok", help="Include successful requests", action='store_true')
    parser.add_argument("--res-nok", help="Include failed requests", action='store_true')
    args = parser.parse_args()
    filepath = pathlib.Path(args.filename)
    with open(filepath) as file:
        first_line = file.readline()
        if first_line.startswith("Device:"):
            os = "ios"
        elif first_line.startswith("App Information"):
            os = "android"
        else:
            os = "unknown"

    if os == "ios":
        print_ios_requests(args, filepath, os) 
    elif os == "android":
        print_android_requests(args, filepath, os) 
    else:
        print("No suitlable logs found!")

if __name__ == "__main__":
    main()