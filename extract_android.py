#!/usr/bin/env python3

import argparse
import pathlib
import fnmatch
import json
import re

s_pattern = '\n'

def format_info(info):
    info_struct = {}
    extracted = info.split(";", 1)
    timestapm = extracted[0]
    url = extracted[1]
    status = re.findall(" - ([0-9]{3})", url)
    status_code = None
    if len(status) > 1:
        status_code = status[0]
    info_struct["timestamp"] = timestapm
    info_struct["status"] = status_code
    info_struct["other"] = url
    return info_struct

def extract_properties(block):
    block_dict = {}
    for i, line in enumerate(block):
        header = line.split(":", 1)
        if len(header) == 2:
            block_dict[header[0]] = header[1]
    return block_dict

def process_request(block):
    request_dict = {}
    request_dict["status"] = 0
    body_index = len(block)
    for i, line in enumerate(block):
        status = re.findall("<-- ([0-9]{3})", line)
        if status is not None and len(status) > 0:
            request_dict["status"] = status[0]
        if re.search("^[\{\"]", line):
            body_index = i
            break
    request_dict["headers"] = extract_properties(block[0:body_index])
    if body_index != len(block):
        body = ("".join(block[body_index:])).strip(s_pattern)
    else:
        body = None
    request_dict["body"] = body
    return request_dict
 
def process_block(block):
    block_dict = {}
    req_index = None
    resp_index = None
    info = format_info(block[0].strip(s_pattern))
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
        block_dict["request"] = process_request(request)
        block_dict["response"]  = process_request(response)
        if info["status"] is None:
            info["status"] = block_dict["response"]["status"]
    return block_dict

def print_entry(block, args):
    print(f'{block["info"]["other"]} - {block["info"]["status"]}')
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

def print_block(block, args):
    block_dict = process_block(block)
    if args.filter:
        text = json.dumps(block_dict)
        if fnmatch.fnmatch(text, args.filter):
            print_entry(block_dict, args)
    else:
        print_entry(block_dict, args)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Path to ios logfile")
    parser.add_argument("--req", help="Include request", action='store_true')
    parser.add_argument("--resp", help="Include response", action='store_true')
    parser.add_argument("--filter", help="String to filter blocks")
    args = parser.parse_args()
    filepath = pathlib.Path(args.filename)
    with open(filepath) as file:
        block = list()
        for line in file:
            if len(block) > 0:
                if len(block) == 1:
                    if "Verbose: ===== Request =====" not in line:
                        print_block(block, args)
                        block.clear()
                        if line.startswith("<-- END HTTP"):
                            block.append(line)
                            print_block(block, args)
                            block.clear()
                        continue
                    else:
                        block.append(line)
                        continue
                elif line.startswith("<-- END HTTP"):
                    print_block(block, args)
                    block.clear()
                else:
                    block.append(line)   
            if "Info: HTTP" in line:
                block.clear()
                block.append(line) 

if __name__ == "__main__":
    main()