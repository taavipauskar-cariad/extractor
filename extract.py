#!/usr/bin/env python3

import argparse
import pathlib
import fnmatch
import json
import re
import copy

s_pattern = '\n'

myaudi_android_timestamp_regex = re.compile("([0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}:[0-9]{3}:)")
myaudi_ios_timestamp_regex = re.compile("([A-Z]{1} [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{3})")
myaudi_android_request_line = re.compile("\[HTTPClient\]")
myaudi_ios_request_line = re.compile("\[HTTPClient\].*\[Client perform")
method_re = re.compile("([0-9]{3})?( - )?([A-Z]{3,}) (.*)")
header_re = re.compile("(\-H) '(.*)'")
body_re = re.compile("(\-d) '(.*)'")
uuid_re = re.compile("UUID (.*)")
android_request_line = re.compile("Info\: HTTP [0-9]{1,} <-")
android_status_regex = re.compile(" - ([0-9]{3})")
android_body_regex = re.compile("^[\{\"]")

block_cache = {}

class Processor:
    def __init__(self):
        pass

    def print_block(self, block, args):
        block_dict = self.process_block(block)
        if block_dict is not None and args.res_ok:
            if int(block_dict["info"]["status"]) < 400:
                self.apply_filter(args, block_dict)
        elif block_dict is not None and args.res_nok:
            if int(block_dict["info"]["status"]) >= 400:
                self.apply_filter(args, block_dict)
        else:
            self.apply_filter(args, block_dict)

    def apply_filter(self, args, block_dict):
        if args.filter:
            text = json.dumps(block_dict)
            if fnmatch.fnmatch(text, args.filter):
                self.print_entry(block_dict, args)
        else:
            self.print_entry(block_dict, args)

    def is_block_in_cache(self, uuid):
        if uuid in block_cache:
            return True
        else:
            return False
        
    def add_block_dict_to_cache(self, uuid, block_dict, action):
        block_cache[uuid] = {action: block_dict}

    def get_cached_block(self, uuid):
        return block_cache.pop(uuid)

class Android(Processor):
    def format_android_info(self, info):
        info_struct = {}
        extracted = info.split(";", 1)
        timestamp = extracted[0]
        url = extracted[1]
        url = url.split(":", 4)[4].strip()
        status = android_status_regex.findall(url)
        status_code = status[0]
        info_struct["timestamp"] = timestamp
        info_struct["status"] = status_code
        info_struct["other"] = url
        return info_struct

    def extract_android_properties(self, block):
        block_dict = {}
        for line in block:
            header = line.split(":", 1)
            if len(header) == 2:
                block_dict[header[0]] = header[1]
        return block_dict

    def process_android_request(self, block):
        request_dict = {}
        body_index = len(block)
        
        for i, line in enumerate(block):
            if android_body_regex.search(line):
                body_index = i
                break
        request_dict["headers"] = self.extract_android_properties(block[0:body_index])
        if body_index != len(block):
            body = ("".join(block[body_index:])).strip(s_pattern)
        else:
            body = None
        request_dict["body"] = body
        return request_dict
    
    def process_block(self, block):
        block_dict = {}
        req_index = None
        resp_index = None
        info = self.format_android_info(block[0].strip(s_pattern))
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
            block_dict["request"] = self.process_android_request(request)
            block_dict["response"]  = self.process_android_request(response)
        return block_dict

    def print_entry(self, block, args):
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

    def print_requests(self, args, filepath):
        with open(filepath) as file:
            block = list()
            for line in file:
                if len(block) > 0:
                    if line.startswith("<-- END HTTP"):
                        self.print_block(block, args)
                        block.clear()
                    else:
                        block.append(line)
                if android_request_line.search(line):
                    block.clear()
                    block.append(line)


class Ios(Processor):
    def extract_ios_properties(self, block):
        block_dict = {}
        for i, line in enumerate(block):
            if line.startswith("["):
                key = line.strip(s_pattern)[1:-1].lower()
                block_dict[key] = block[i + 1].strip(s_pattern).lower()
        return block_dict

    def process_ios_request(self, block):
        request_dict = {}
        headers_index = None
        body_index = None
        for i, line in enumerate(block):
            if line.startswith("### Headers"): headers_index = i
            if line.startswith("### Body"): body_index = i
        request_dict["headers"] = self.extract_ios_properties(block[headers_index:body_index])
        body = ("".join(block[body_index + 2:])).strip(s_pattern)
        if "Request body is empty" in body:
            request_dict["body"] = ""
        else:
            request_dict["body"] = body
        return request_dict
    
    def process_block(self, block):
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
        block_dict["info"] = self.extract_ios_properties(info)
        block_dict["request"] = self.process_ios_request(request)
        block_dict["response"]  = self.process_ios_request(response)
        if block_dict.get("info", {}).get("status") is None:
            block_dict["info"]["status"] = 0
        return block_dict

    def print_entry(self, block, args):
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

    def print_requests(self, args, filepath):
        with open(filepath) as file:
            block = list()
            for line in file:
                if line.startswith("## INFO"):
                    block.clear()
                    block.append(line)
                if line.startswith("------------------------------"):
                    self.print_block(block, args)
                if len(block) > 0:
                    block.append(line)

class MyAudiAndroid(Processor):
    def print_requests(self, args, filepath):
        with open(filepath) as file:
            block = list()
            for line in file:
                if len(block) > 0:
                    if myaudi_android_timestamp_regex.search(line):
                        self.print_block(block, args)
                        block.clear()
                    else:
                        block.append(line)
                if myaudi_android_request_line.search(line):
                    block.clear()
                    block.append(line)

    def extract_myaudi_headers(self, block):
        block_dict = {}
        timestamp = myaudi_android_timestamp_regex.search(block[0]).group(0)
        block_dict["request date"] = timestamp
        method = method_re.search(block[1]).group(3)
        status = method_re.search(block[1]).group(1)
        url = method_re.search(block[1]).group(4)
        block_dict["method"] = method
        block_dict["status"] = status
        block_dict["url"] = url
        
        for line in block:
            match = header_re.search(line)
            if match:
                header = match.group(2).split(":", 1)
                if len(header) == 2:
                    block_dict[header[0].strip()] = header[1].strip()
        return block_dict

    def extract_myaudi_request(self, block):
        request_dict = {}
        body = ""
        for line in block:
            match = body_re.search(line)
            if match:
                body = match.group(0).strip()
        request_dict["body"] = body
        return request_dict

    def extract_myaudi_response(self, block):
        response_dict = {}
        body = ""
        bodyIndex = None
        for i, line in enumerate(block):
            if line.startswith("\n"):
                bodyIndex = i
                break
        if bodyIndex is not None:
            body = block[bodyIndex+1:]
        response_dict["body"] = body
        return response_dict
                
    def process_block(self, block):
        block_dict = {}
        uuid = uuid_re.search(block[0]).group(1)
        if " Request for " in block[0]:
            request_block = copy.deepcopy(block)
            block_dict.update({"request": request_block})
            if not self.is_block_in_cache(uuid):
                self.add_block_dict_to_cache(uuid, request_block, "tmp")

        elif " Response for " in block[0]:
            response_block = copy.deepcopy(block)
            block_dict.update({"response": response_block})
            if self.is_block_in_cache(uuid):
                cached_block = self.get_cached_block(uuid)
                block_dict.update({"request": cached_block["tmp"]})
                block_dict["info"] = self.extract_myaudi_headers(block_dict["response"])
                block_dict["request"] = self.extract_myaudi_request(block_dict["request"])
                block_dict["response"] = self.extract_myaudi_response(block_dict["response"])
        
        if block_dict is not None and "request" in block_dict and "response" in block_dict:    
                return block_dict
        else:
                return None

    def print_entry(self, block, args):
        if block is not None:
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

class MyAudiIos(Processor):
    def print_requests(self, args, filepath):
        with open(filepath) as file:
            block = list()
            for line in file:
                if len(block) > 0:
                    if myaudi_ios_timestamp_regex.search(line):
                        self.print_block(block, args)
                        block.clear()
                    else:
                        block.append(line)
                if myaudi_ios_request_line.search(line):
                    block.clear()
                    block.append(line)

    def process_block(self, block):
        block_dict = {}
        uuid = uuid_re.search(block[0]).group(1)
        if " Performing request " in block[0]:
            request_block = copy.deepcopy(block)
            block_dict.update({"request": request_block})
            if not self.is_block_in_cache(uuid):
                self.add_block_dict_to_cache(uuid, request_block, "tmp")

        elif " Response for " in block[0]:
            response_block = copy.deepcopy(block)
            block_dict.update({"response": response_block})
            if self.is_block_in_cache(uuid):
                cached_block = self.get_cached_block(uuid)
                block_dict.update({"request": cached_block["tmp"]})
                block_dict["info"] = self.extract_myaudi_ios_headers(block_dict["response"])
                block_dict["request"] = self.extract_myaudi_ios_request(block_dict["request"])
                block_dict["response"] = self.extract_myaudi_ios_response(block_dict["response"])
        
        if block_dict is not None and "request" in block_dict and "response" in block_dict:    
            return block_dict
        else:
            return None
        
    def extract_myaudi_ios_headers(self, block):
        block_dict = {}
        method = method_re.search(block[1]).group(3)
        status = method_re.search(block[1]).group(1)
        url = method_re.search(block[1]).group(4)
        block_dict["method"] = method
        block_dict["status"] = status
        block_dict["url"] = url
        
        for line in block:
            header = line.split(":", 1)
            if len(header) == 2:
                block_dict[header[0]] = header[1]
        block_dict["request date"] = block_dict["Date"].strip()
        return block_dict
    
    def extract_myaudi_ios_request(self, block):
        request_dict = {}
        body = ""
        for line in block:
            match = body_re.search(line)
            if match:
                body = match.group(0).strip()
        request_dict["body"] = body
        return request_dict

    def extract_myaudi_ios_response(self, block):
        response_dict = {}
        body = ""
        bodyIndex = None
        for i, line in enumerate(block):
            if line.startswith("\n"):
                bodyIndex = i
                break
        if bodyIndex is not None:
            body = block[bodyIndex+1:]
        response_dict["body"] = body
        return response_dict


    def print_entry(self, block, args):
        if block is not None:
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

def main():
    os = None
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Path to logfile")
    parser.add_argument("--req", help="Include request", action='store_true')
    parser.add_argument("--resp", help="Include response", action='store_true')
    parser.add_argument("--filter", help="Unix-Shell wildcard string to filter blocks, example: '*\"Method\": \"POST\"*' ")
    parser.add_argument("--res-ok", help="Include successful requests", action='store_true')
    parser.add_argument("--res-nok", help="Include failed requests", action='store_true')
    args = parser.parse_args()
    filepath = pathlib.Path(args.filename)
    with open(filepath) as file:
        first_line = file.readline()
        if "OneTouchApp" in first_line:
            for i, l in enumerate(file, start=1):
                if i == 1:
                    first_line = l
                    break
                
        if first_line.startswith("Device:"):
            os = "ios"
        elif first_line.startswith("App Information"):
            os = "android"
        elif first_line.startswith("Log de.myaudi"):
            os = "myaudi_android"
        elif first_line.startswith("App: myAudi"):
            os = "myaudi_ios"
        else:
            print(first_line)
            os = "unknown"
            exit(1)

    if os == "ios":
        processor = Ios()
    elif os == "android":
        processor = Android()
    elif os == "myaudi_android":
        processor = MyAudiAndroid()
    elif os == "myaudi_ios":
        processor = MyAudiIos()
    else:
        print("No suitlable logs found!")

    processor.print_requests(args, filepath)

if __name__ == "__main__":
    main()