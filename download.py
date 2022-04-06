#!/usr/bin/env python3
"""
download.py: Fetch publicly accessible building codes from the International
Code Council's API.

Documents are downloaded by numerical document ID, which can be obtained from
the web interface URL like this:

WEB_URL="https://codes.iccsafe.org/content/NCBC2018"
curl $WEB_URL | grep documentid | tr -d ' a-z="'

"""

import argparse
import sys
import os

from typing import Iterator, Dict, List, Tuple

from api import APIClient

def parse_args(args: List[str]) -> argparse.Namespace:
    """
    Parse command-line options
    """
    
    # Make parser with formatted docstring for help.
    parser = argparse.ArgumentParser(description=__doc__, 
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument("document_id", type=int,
        help="Document ID of the document to download.")
    parser.add_argument("--base-directory", type=str, default=".",
        help=("Directory into which to download the document. An api/ "
        "directory will be created here and API responses will be saved."))
    parser.add_argument("--combined-document", type=argparse.FileType('w'),
        help=("Save combined XML to this file"))
    
    return parser.parse_args(args[1:])
    
def main(args: List[str]) -> int:
    """
    Main entry point of the program.
    """
    
    options = parse_args(args)
    
    api = APIClient(options.base_directory)
    document_id = options.document_id
    # We may be combining to a stream
    combined_document = options.combined_document
    
    info = api.get_info(document_id)
    title = info.get('title')
    print(f"Downloading document {document_id}: {title}")
    content_type = info.get('content_type')
    if content_type is not None and content_type != "ICC XML":
        print(f"Error: we only support ICC XML documents, but content_type is {content_type}")
        sys.exit(1)
        
    if combined_document:
        combined_document.write(f'<html>\n<head>\n<title>{title}</title>\n</head>\n<body>\n<h1>{title}</h1>\n')
        
    entry_count = 0
    for _ in api.for_each_content_id(document_id):
        entry_count += 1
    print(f"Going to download {entry_count} entries...")
    
    for i, (content_id, section_title) in enumerate(api.for_each_content_parsed(document_id)):
        print(f"Downloading content {i}/{entry_count}: {content_id}: {section_title}")
        content = api.get_content(document_id, content_id)
        print(f"Content: \"{content[:1024]}\"...")
        
        if combined_document:
            combined_document.write('\n')
            combined_document.write(content)
            combined_document.write('\n')
            combined_document.flush()
        
        break
        
    if combined_document:
        combined_document.write(f'\n</body></html>\n')
    
    return 0
    
    

if __name__ == "__main__":
    sys.exit(main(sys.argv))

