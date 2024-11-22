#!/usr/bin/env python3

import argparse
import pathlib
import fnmatch
import json

s_pattern = '\n'

def extract_properties(block):
    block_dict = {
        "Status": "0" # Sometimes status is missing
    }
    for i, line in enumerate(block):
        if line.startswith("["):
            key = line.strip(s_pattern)[1:-1]
            block_dict[key] = block[i + 1].strip(s_pattern)
    return block_dict

def process_request(block):
    request_dict = {}
    headers_index = None
    body_index = None
    for i, line in enumerate(block):
        if line.startswith("### Headers"): headers_index = i
        if line.startswith("### Body"): body_index = i
    request_dict["headers"] = extract_properties(block[headers_index:body_index])
    body = ("".join(block[body_index + 2:])).strip(s_pattern)
    if "Request body is empty" in body:
        request_dict["body"] = ""
    else:
        request_dict["body"] = body
    return request_dict
 
def process_block(block):
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
    block_dict["info"] = extract_properties(info)
    block_dict["request"] = process_request(request)
    block_dict["response"]  = process_request(response)
    return block_dict

def print_entry(block, args):
    print(f'{block["info"]["Request date"]}: {block["info"]["Method"]}:{block["info"]["Status"]} {block["info"]["URL"]}')
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

def print_block(block, args):
    if args.filter:
        text = json.dumps(block)
        if fnmatch.fnmatch(text, args.filter):
            print_entry(block, args)
    else:
        print_entry(block, args)

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
            if line.startswith("## INFO"):
                block.clear()
                block.append(line)
            if line.startswith("------------------------------"):
                block_dict = process_block(block)
                print_block(block_dict, args)
            if len(block) > 0:
                block.append(line)   

if __name__ == "__main__":
    main()