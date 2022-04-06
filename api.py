import sys
import math
import os
import urllib.request
from urllib.error import URLError
import json
import time
import tempfile
from datetime import datetime, timedelta

from typing import Iterator, Dict, List, Tuple

"""
api.py: Bindings for the International Code Council's API.
"""

class TokenBucket:
    """
    A token-bucket rate limiter for accessing APIs safely.
    """
    
    def __init__(self, token_period: float, token_limit: int) -> None:
        """
        Make a new buckrt that gets a token every token_period seconds, up to
        token_limit.
        """
        
        self.tokens = 0
        self.token_period = token_period
        self.token_limit = token_limit
        self.current_to = datetime.now()
        
    def take(self) -> None:
        """
        Wait until a token is available and then take it.
        """
        
        # True up token count
        now = datetime.now()
        # Work out how long it has been since the last time we issued a token for
        elapsed_time = now - self.current_to
        # Figure out how many whole periods to do
        elapsed_periods = elapsed_time.total_seconds() / token_period
        whole_periods = int(math.floor(elapsed_periods))
        # Figure out the remaining partial period
        unused_seconds = (elapsed_periods - whole_periods) * self.token_period
        unused_time = timedelta(seconds=unused_seconds)
        # Record the time we will be current to after issuing the tokens
        self.current_to = now - unused_time
        
        # Issue the tokens
        self.tokens = min(self.token_limit, self.tokens + whole_periods)
        
        if self.tokens <= 0:
            # We need to wait for a token.
            # So wait to the end of the current period
            remaining_time = self.token_period - unused_seconds
            time.sleep(remaining_time)
            # And recurse
            self.take()
        else:
            # Debit a token and return now
            self.tokens -= 1
        
    

class APIClient:
    """
    Caching API bindings for the ICC REST API/directory structure.
    
    Because everything is laid out in a nice RESTful folder structure, and the
    content ought to be static, we can just cache data on disk as files and
    save bandwidth and latency when we want the same thing again later.
    """
    def __init__(self, base_directory: str, token_period: float = 1, token_limit: int = 5) -> None:
        """
        Make a new proxy.
        
        :param base_directory: The directory to cache the API responses in.
        :param token_period: Maximum sustained request rate, in seconds per request.
        :param token_limit: Maximum burst request rate, in immediate requests.
        """
        self.api_directory = os.path.join(base_directory, 'api')
        os.makedirs(self.api_directory, exist_ok=True)
        self.base_url = 'https://codes.iccsafe.org/api/'
        self.limiter = TokenBucket(token_period, token_limit)
        
    def fetch(self, relative_url: str) -> str:
        """
        Fetch content from the given relative URL. Save it, and also return the
        data.
        
        Relative URL should not include leading 'api' or leading '/'.
        """
        
        assert '..' not in relative_url
        
        # Figure out what we want
        full_url = self.base_url + relative_url
        
        # Figure out where to cache
        destination_path = os.path.join(self.api_directory, relative_url)
        
        if os.path.exists(destination_path):
            print(f"Use cached: {full_url}")
            with open(destination_path, 'rb') as in_file:
                # Read the whole file. If it's there, it must be complete.
                content = in_file.read()
        else:
            # We need to download and cache.
            print(f"Fetch: {full_url}")
            # Don't go too fast
            self.limiter.take()
            # Make sure parent directory exists
            destination_parent = os.path.dirname(destination_path)
            os.makedirs(destination_parent, exist_ok=True)
            
            # Make a temp file to download to. THe API endpoints never look
            # like this so it can't conflict.
            temp_path = os.mkstemp(dir=destination_parent) 
            
            with urllib.request.urlopen(full_url) as response:
                # Check the status
                status = response.status
                reason = response.reason
                print(f"Response: {status} {reason}")
                if status != 200:
                    raise URLError(reason)
                # Get the content
                content = response.read()
                
            with open(temp_path, 'wb') as out_file:
                out_file.write(content)
                
            # Now that the file is complete, move it into place for other cache
            # users.
            os.rename(temp_path, destination_path)
        
        return content.decode('utf-8')
        
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
        
    def get_toc(self, document_id: int) -> List[dict]:
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
                
    def for_each_content_parsed(self, document_id: int) -> Iterator[Tuple[int, str]]:
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
