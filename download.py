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
import urllib.request
import json
import time

from typing import Iterator

def parse_args(args: list[str]):
    """
    Parse command-line options
    """
    
    # Make parser with formatted docstring for help.
    parser = argparse.ArgumentParser(description=__doc__, 
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument("document-id", type=int, required=True,
        help="Document ID of the document to download.")
    parser.add_argument("--base-directory", type=str, default=".",
        help=("Directory into which to download the document. An api/ "
        "directory will be created here and API responses will be saved."))
    
    return parser.parse_args(args[1:])
    
    
class APIProxy:
    """
    Caching proxy over the ICC API.
    """
    def __init__(self, base_directory: str):
        """
        Make a new proxy.
        
        :param base_directory: The directory to cache the API responses in.
        """
        self.api_directory = os.path.join(base_directory, 'api')
        os.makedirs(self.api_directory, exists_ok=True)
        self.base_url = 'https://codes.iccsafe.org/api/'
        
    def fetch(self, relative_url: str) -> str:
        """
        Fetch content from the given relative URL. Save it, and also return the
        data.
        
        Relative URL should not include leading 'api' or leading '/'.
        """
        
        assert '..' not in relative_url
        
        # Figure out where to write
        destination_path = os.path.join(self.api_directory, relative_url)
        
        # TODO: Fulfill from local cache if there
        # TODO: Write to a temp file and move into place if not
        
        # Make sure parent directory exists
        destination_parent = os.path.dirname(destination_path)
        os.makedirs(destination_parent, exists_ok=True)
        
        with urllib.request.urlopen(self.base_url + '/' + relative_url) as response:
            # Get the content
            content = response.read()
            
        with open(destination_path, 'w') as out_file:
            out_file.write(content)
        
        # Rate limit
        time.sleep(5)
        
        return content
        
    def get_info(self, document_id: int) -> dict:
        """
        Get the document info JSON for the given document and parse it.
        
        Info dict has among other fields a 'title', and a 'content_type' which
        should probably be "ICC XML" if this tool is going to work.
        """
        
        info_json = self.fetch(f'content/info/{document_id}')
        info = json.loads(info_json)
        assert isinstance(info, dict)
        return info
        
    def get_toc(self, document_id: int) -> list[dict]:
        """
        Get the document table of contents JSON for the given document and
        parse it.
        
        TOC is an array of dicts, which have a 'content_id' unquoted number,
        and probably either 'title' or a 'link' with a 'title'. They can have
        'sub_sections' which is a similar array.
        """
        
        toc_json = self.fetch(f'content/chapters/{document_id}')
        toc = json.loads(toc_json)
        assert isinstance(toc, list)
        return toc
        
     def get_content(self, document_id: int, content_id: int) -> str:
        """
        Get the string containing the XML content for part of the document.
        """
        
        content_json = self.fetch(f'content/chapter-xml/{document_id}/{content_id}')
        content = json.loads(content_json)
        assert isinstance(content, str)
        return content
        
    def for_each_content_id(self, document_id: int) -> Iterator[int]:
        """
        Loop over the content IDs of all the nested table of contents items in
        the given document.
        """
        
        for content_id, _ in self.for_each_content_parsed(document_id):
            yield content_id
                
    def for_each_content_parsed(self, document_id: int) -> Iterator[tuple[int, str]]:
        """
        Loop over pairs of the content IDs and section titles of all the nested
        table of contents items in the given document.
        """
        
        for toc_entry in self.for_each_content_entry(document_id):
            content_id = toc_entry.get('content_id')
            if content_id is not None and isinstance(content_id, int):
                # We have to send this. Does it have a title?
                title = toc_entry.get('title')
                if title is None or not isinstance(title, str):
                    # Maybe it has a link with a title instead
                    title = toc_entry.get('link', {}).get('title')
                if not isinstance(title, str):
                    title = None
                yield content_id, title
                
        
     def for_each_content_entry(self, document_id: int) -> Iterator[dict]:
        """
        Loop over the ToC entry dicts of all the nested table of contents items
        in the given document.
        """
        
        toc = self.get_toc(document_id)
        assert isinstance(toc, list)
        
        def for_each_child_recursive(toc_dict: dict) -> Iterator[dict]:
            """
            Go through each child TOC dict under the given one and yield it.
            Then yield all its children recursively.
            """
            children = toc_dict.get('sub_sections')
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        yield child
                        for subchild in for_each_child_recursive(child):
                            yield subchild
        
        for root_item in toc:
            if isinstance(root_item, dict):
                yield root_item
                for nested_item in for_each_child_recursive(root_item):
                    yield nested_item 
            
            
            
        
            
def main(args: list[str]) -> int:
    """
    Main entry point of the program.
    """
    
    options = parse_args(args)
    
    api = APIProxy(options.base_directory)
    document_id = options.document_id
    
    info = api.get_info(document_id)
    title = info.get('title')
    print(f"Downloading document {document_id}: {title}")
    
    for content_id, section_title in api.for_each_content_parsed(document_id):
        print(f"Downloading content {content_id}: {section_title}")
        content = api.get_content(document_id, content_id)
        print(f"Content: {content[:100]}")
        sys.exit(1)
    
    return 0
    
    

if __name__ == "__main__":
    sys.exit(main(sys.argv))

