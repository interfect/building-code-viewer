"""
fragment_parser.py: Parsing utilities for dealing with markup fragments
"""

from typing import Any, Dict, Iterator, List, Tuple, Optional, Union

# We can't use e.g. pulldom or (probably) elementtree because they expect to be able to e.g. resolve entities and namespaces, and the fragments lack the doctype stuff to be able to do that.
# We should use Beautiful Soup, but we can't because that would add a non-standard-library dependency and thus an install process.
# So we just parse character by character.

class Element:
    """
    An element in a parse tree.
    """
    
    def __init__(self):
        self.tag_name = None
        # Is this a self-closing tag?
        self.is_self_closing = False
        # Is this tag closed (implicit closing tag)
        self.is_closed = False
        # Is this tag itself a closing tag? Shouldn't appear in a tree.
        self.is_closing = False
        # Attributes are tuples of name and value, where value may be None.
        # Values include their own quotes.
        self.attributes = []
        # Children are other elements and strings
        self.children = []
        
    def __repr__(self):
        return f'<{self.tag_name} {self.attributes}{"/" if self.is_self_closing else ""}>{self.children}{("</" + self.tag_name + ">") if self.is_closed else ""}'
        
    def write_to(self, stream, indent='', add_indent='', newline=''):
        """
        Write to a stream.
        
        Note that using the pretty-printing will insert new whitespace in the
        document where it isn't wanted.
        TODO: Fix this.
        """
        
        stream.write(indent)
        stream.write('<')
        if self.is_closing:
            stream.write('/')
        if self.tag_name:
            stream.write(self.tag_name)
        for attribute, value in self.attributes:
            stream.write(' ')
            stream.write(attribute)
            if value is not None:
                stream.write('=')
                stream.write(value)
        if self.is_self_closing:
            stream.write('/')
        stream.write('>')
        if len(self.children) > 0:
            stream.write(newline)
        for child in self.children:
            if isinstance(child, Element):
                child.write_to(stream, indent=indent + add_indent, add_indent=add_indent, newline=newline)
                stream.write(newline)
                indented = False
            else:
                stream.write(indent + add_indent)
                stream.write(child)
                stream.write(newline)
        if self.is_closed:
            stream.write(indent)
            stream.write('</')
            if self.tag_name:
                stream.write(self.tag_name)
            stream.write('>')

def parse_to_stream(data: str) -> Iterator[Tuple[str, Optional[str]]]:
    """
    Parse markup to a series of events:
    
    'CHARACTERS', text
    'START_TAG', None
    'TAG_IS_CLOSING', None
    'TAG_IS_SELF_CLOSING', None
    'NAME', attribute or tag name
    'ATTRIBUTE_VALUE', attribute value (possibly quoted)
    'END_TAG', None
    
    We don't do lookahead and so can't handle comments and scripts properly.
    
    """
    
    WHITESPACE = [' ', '\t', '\n']
    
    cursor = 0
    # The states would be:
    # states = ['TEXT', 'IN_TAG_START', 'IN_NAME', 'IN_VALUE_START', 'IN_VALUE', 'IN_DOUBLE_QUOTED_VALUE', 'IN_SINGLE_QUOTED_VALUE', 'IN_TAG']
    state = 'TEXT'
    current_item_chars = []
    
    def finish():
        # Finish anything that accumulates characters (text, tag name, attribute value)
        if state == 'TEXT':
            result = ('CHARACTERS', ''.join(current_item_chars))
        elif state == 'IN_NAME':
            result = ('NAME', ''.join(current_item_chars))
        elif state in ['IN_VALUE', 'IN_VALUE_START']:
            result = ('ATTRIBUTE_VALUE', ''.join(current_item_chars))
        else:
            raise RuntimeError("Cannot finish " + state)
        current_item_chars.clear()
        return result
       
        
    
    while cursor < len(data):
        char_here = data[cursor]
        #print(f'State: {state}, char: {char_here}, item: {current_item_chars}')
        if state == 'TEXT':
            # In normal text
            if char_here == '<':
                yield finish()
                yield 'START_TAG', None
                state = 'IN_TAG_START'
            else:
                current_item_chars.append(char_here)
        elif state == 'IN_TAG_START':
            if char_here == '/':
                # This is a close tag
                yield 'TAG_IS_CLOSING', None
            elif char_here in WHITESPACE:
                # Can have whitespace before the tag name
                pass
            else:
                # Start parsing the name
                state = 'IN_NAME'
                current_item_chars.append(char_here)
        elif state == 'IN_NAME':
            # Parsing a tag or attribute name
            if char_here == '>':
                # It's over
                yield finish()
                yield 'END_TAG', None
                state = 'TEXT'
            elif char_here == '/':
                # It's marked as a closing tag. Probably.
                yield finish()
                yield 'TAG_IS_SELF_CLOSING', None
                state = 'IN_TAG'
            elif char_here == '=':
                # It's over, go to value
                yield finish()
                state = 'IN_VALUE_START'
            elif char_here in WHITESPACE:
                # It's over
                yield finish()
                state = 'IN_TAG'
            else:
                # Name content
                current_item_chars.append(char_here)
        elif state == 'IN_TAG':
            if char_here == '>':
                # Tag is over
                yield 'END_TAG', None
                state = 'TEXT'
            elif char_here == '/':
                # Tag is closing but not at the start
                yield 'TAG_IS_SELF_CLOSING', None
                state = 'IN_TAG'
            elif char_here in WHITESPACE:
                # Skip whitespace
                pass
            elif char_here == '=':
                # Starting a value, skip leading whitespace
                state = 'IN_VALUE_START'
            else:
                # Starting a name
                state = 'IN_NAME'
                current_item_chars.append(char_here)
        elif state == 'IN_VALUE_START':
            if char_here == '"':
                # Open double quote
                current_item_chars.append(char_here)
                state = 'IN_DOUBLE_QUOTED_VALUE'
            elif char_here == '\'':
                # Open single quote
                current_item_chars.append(char_here)
                state = 'IN_SINGLE_QUOTED_VALUE'
            elif char_here in WHITESPACE:
                # Whitespace is ignored
                pass
            elif char_here == '/':
                # Value is empty.
                # Tag is going to close itself
                # TODO: Do we need to lookahead for > because we might say value=/ ?
                yield finish()
                yield 'TAG_IS_SELF_CLOSING', None
                state = 'IN_TAG'
            elif char_here == '>':
                # Value is empty
                # Tag is over
                yield finish()
                yield 'END_TAG', None
                state = 'TEXT'
            else:
                # This is content
                state = 'IN_VALUE'
                current_item_chars.append(char_here)
        elif state == 'IN_VALUE':
            if char_here == '"':
                # Open double quote
                current_item_chars.append(char_here)
                state = 'IN_DOUBLE_QUOTED_VALUE'
            elif char_here == '\'':
                # Open single quote
                current_item_chars.append(char_here)
                state = 'IN_SINGLE_QUOTED_VALUE'
            elif char_here in WHITESPACE:
                # Whitespace ends the value
                yield finish()
                state = 'IN_TAG'
            elif char_here == '/':
                # Tag is going to close itself
                # TODO: Do we need to lookahead for > because we might say value=/ ?
                yield finish()
                yield 'TAG_IS_SELF_CLOSING', None
                state = 'IN_TAG'
            elif char_here == '>':
                # Tag is over
                yield finish()
                yield 'END_TAG', None
                state = 'TEXT'
            else:
                # This is content
                current_item_chars.append(char_here)
        elif state == 'IN_DOUBLE_QUOTED_VALUE':
            if char_here == '"':
                # Close double quote
                current_item_chars.append(char_here)
                state = 'IN_VALUE'
            else:
                # This is content
                current_item_chars.append(char_here)
        elif state == 'IN_SINGLE_QUOTED_VALUE':
            if char_here == '\'':
                # Close single quote
                current_item_chars.append(char_here)
                state = 'IN_VALUE'
            else:
                # This is content
                current_item_chars.append(char_here)
        else:
            raise RuntimeError("Unimplemented state: " + state)
        
        #print(f'State: {state}, item: {current_item_chars}')
        
        cursor += 1
    
    #print(f'End state: {state}, item: {current_item_chars}')
    
    # Now we're done scanning the text
    yield finish()
        
        
def parse_to_subtrees(fragment: str) -> List[Union[Element, str]]:
    """
    Parse an HTML or XML fragment, which may lack closing tags, to a list of
    Elements or strings.
    """
    
    # We maintain a stack of the tree we are building. Only not-yet-closed
    # elements should be here.
    stack: List[Element] = []
    
    # We also maintain a current tag. If it turns out to be the same name
    # as the bottom tag on the stack, and closing, we close it.
    current_tag = None
    
    # And a current attribute, as either None or a list of a name and a possibly-None value
    current_attribute = None
    
    # And when the base of the stack closes we put it in this list, since
    # we aren't making a root node.
    output: List[Union[Element, str]] = []
    
    # Get an iterable of events for the open and close tags and text nodes
    # in the document
    stream = parse_to_stream(fragment)
    for event_type, event_text in stream:
        if event_type == 'CHARACTERS':
            # Handle document text
            if len(event_text) > 0:
                if len(stack) == 0:
                    # It is top-level
                    output.append(event_text)
                else:
                    # It belongs in the current unclosed tag
                    stack[-1].children.append(event_text)
        elif event_type == 'START_TAG':
            # We are starting a new tag
            assert current_tag is None
            current_tag = Element()
        elif event_type == 'TAG_IS_CLOSING':
            assert current_tag is not None
            current_tag.is_closing = True
        elif event_type == 'TAG_IS_SELF_CLOSING':
            assert current_tag is not None
            current_tag.is_self_closing = True
        elif event_type == 'NAME':
            assert current_tag is not None
            if current_tag.tag_name is None:
                # First name names the tag
                current_tag.tag_name = event_text
            else:
                # Starting an attribute
                if current_attribute is not None:
                    current_tag.attributes.append(tuple(current_attribute))
                current_attribute = [event_text, None]
        elif event_type == 'ATTRIBUTE_VALUE':
            assert current_attribute is not None
            current_attribute[1] = event_text
        elif event_type == 'END_TAG':
            assert current_tag is not None
            if current_attribute is not None:
                current_tag.attributes.append(tuple(current_attribute))
                current_attribute = None
            if len(stack) > 0 and current_tag.is_closing:
                if current_tag.tag_name != stack[-1].tag_name:
                    # Complain about a mismatch
                    print(f"Closing {stack[-1].tag_name} with {current_tag.tag_name}")
                # This is a closing tag we want. Throw out its stuff and
                # just close the tag it closes.
                tag_closed = stack.pop()
                tag_closed.is_closed = True
                if len(stack) > 0:
                    # This becomes a child of the next thing up
                    stack[-1].children.append(tag_closed)
                else:
                    # This becomes a root element
                    output.append(tag_closed)
            elif current_tag.is_self_closing:
                # This tag is a leaf
                if len(stack) > 0:
                    # This becomes a child of the next thing up
                    stack[-1].children.append(current_tag)
                else:
                    # This becomes a root element
                    output.append(current_tag)
            elif current_tag.is_closing:
                # This is an unwanted closing tag
                raise RuntimeError(f"Unexpected closing {current_tag.tag_name}")
            else:
                # This is an opening tag
                stack.append(current_tag)
                
            current_tag = None
        else:
            raise RuntimeError(f"Unimplemented event: {event_type}")
                
    
    if current_tag is not None:
        raise RuntimeError("Partial final tag")
    
    while len(stack) > 0:
        # Now handle all the unclosed tags
        unclosed_tag = stack.pop()
        if len(stack) > 0:
            # Make it a child of the next thing up
            stack[-1].children.append(unclosed_tag)
        else:
            # Make it output
            output.append(unclosed_tag)
            
    # Then after we have finished iterating or stopped 
    return output
            
