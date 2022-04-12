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
import textwrap

from typing import Iterator, Dict, List, Tuple

from api import APIClient
from fragment_parser import Element, parse_to_subtrees

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
    parser.add_argument("--max-sections", type=int, default=float('inf'),
        help=("Only process this many sections"))
    
    return parser.parse_args(args[1:])
    
def main(args: List[str]) -> int:
    """
    Main entry point of the program.
    """
    
    options = parse_args(args)
    
    # Set up the API client
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
        combined_document.write('<html>\n<head>\n')
        combined_document.write(f'<title>{title}</title>\n')
        combined_document.write(textwrap.dedent("""
        <style type="text/css">
            * {
                padding: 0;
                margin: 0;
            }
            body {
                line-height: 1.5;
                margin: 1em;
            }
            .content_bold, .bold {
                font-weight: bold;
            }
            .italic, .pubname {
                font-style: italic;
            }
            .write_on_line {
                text-decoration: underline;
            }
            .content_center, .center, .frontmatter_title {
                width: 100%;
                text-align: center;
                display: table;
            }
            .content_indent_first {
                text-indent: 5em;
            }
            .content_newline_inside_td {
                display: list-item;
                list-style: none;
                width: 100%;
            }
            .frontmatter_title {
                font-size: 125%;
            }
            .frontmatter_subhead, .frontmatter_title {
                font-family: sans-serif;
                margin-top: 1em;
                margin-bottom: 1em;
            }
            .v-card {
            }
            /* All the headings are h1 and they are sized down by the browser according to section nesting */
            h1 {
                margin-top: 1em;
                margin-bottom: 1em;
            }
            h1.chapter {
                font-size: 20pt;
                text-align: center;
            }
            h1.subchapter {
                font-size: 18pt;
                text-align: center;
            }
            h1.level1 {
                font-size: 16pt;
                text-align: center;
            }
            h1.level2 {
                font-size: 14pt;
            }
            h1.level3 {
                font-size: 12pt;
            }
            .section_number::before, .section_number::after, .chapter_number::before, .chapter_number::after, span.label::after, .run_in span.bold::after {
                content: " ";
            }
            ol, ul {
                padding-left: 2em;
            }
            ol.no_mark, ul.no_mark {
                list-style-type: none;
            }
            th {
                font-family: sans-serif;
            }
            td, th {
                padding: 0.25em;
            }
            section.level3 {
                margin-left: 2em;
            }
            .exception {
                margin-left: 2em;
                margin-top: 1em;
            }
            .changed_ICC {
                color: #008;
            }
            a.section_reference, a.section_reference_standard {
            }
            p {
                margin-bottom: 0.5em;
                text-align: justify;
            }
            table {
                width: 100%;
                margin-top: 1em;
                margin-bottom: 1em;
                border-collapse: collapse;
            }
            .list dt {
                width: 40%;
                display: inline-block;
            }
            .list dd {
                width: 60%;
                display: inline-block;
            }
        </style>
        """.strip()))
        combined_document.write('</head>\n<body>\n')
        
    entry_count = 0
    for _ in api.for_each_content_entry(document_id):
        entry_count += 1
    print(f"Going to download {entry_count} entries...")
    
    # Sections with children need their tags closed when we leave them.
    last_nesting_level = 0
    
    for i, (nesting_level, content_id, section_title) in enumerate(api.for_each_content_parsed(document_id)):
        if nesting_level != last_nesting_level:
            print(f"Changing nesting level {last_nesting_level} -> {nesting_level}")
        print(f"Downloading content {i}/{entry_count} at level {nesting_level}: {content_id}: {section_title}")
        content = api.get_content(document_id, content_id)
        
        if combined_document:
            # Now parse, accepting unterminated tags
            top_level_nodes = parse_to_subtrees(content)
            for node in top_level_nodes:
                # TODO: Actually nest?
                if isinstance(node, Element):
                    # It's a subtree
                    if (not node.is_self_closing) and (not node.is_closed):
                        # Make it closed
                        print(f"Closing unclosed {node.tag_name} tag")
                        node.is_closed = True
                    node.write_to(combined_document)
                    combined_document.write('\n')
                else:
                    # It's just text
                    combined_document.write(node)
                    combined_document.write('\n')
            combined_document.flush()
        
        last_nesting_level = nesting_level
        
        if i + 1 >= options.max_sections:
            break
        
    # Finish the last nesting level
    for levels_removed in range(last_nesting_level):
        for _ in range(nesting_level - levels_removed):
            # Indent the close
            combined_document.write('    ')
        combined_document.write('</section>\n')
    
        
    if combined_document:
        combined_document.write(f'\n</body>\n</html>\n')
    
    return 0
    
    

if __name__ == "__main__":
    sys.exit(main(sys.argv))

