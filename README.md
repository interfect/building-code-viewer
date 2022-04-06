# Building Code Viewer

This project contains tools for viewing building codes adopted by US states and hosted by the International Code Council (ICC).

The ICC is a private organization that writes, and owns the copyright to, the International Building Code (IBC). States adopt the IBC as their own state building code, often with state-specific modifications. However, since the resulting state code is substantially the same as the privately-owned IBC, it can be difficult to read. The full state code might be publicly available as a physical reference book at a government office. The ICC also often makes the resulting state codes, as amended, available for viewing on their web site.

The ICC web viewer lacks important features, such as the ability to print pages, copy snippets into another document, or search the code. However, the ICC also publishes the codes available through their web viewer through an (apparently undocumented but quite simple) API, so they do not in fact need to be viewed through a browser using the underpowered ICC web viewer.

This project contains tools to access ICC-hosted building codes through the ICC API, to provide a better code-reading experience than is available to the public on the ICC web site.

## Document IDs

All of the tools use "document IDs". You will need the document ID for the building code you want to look at. If you have an ICC web viewer URL, you can convert it to a document ID by running something like this:

```bash
WEB_URL="https://codes.iccsafe.org/content/NCBC2018"
curl $WEB_URL | grep documentid | tr -d ' a-z="'
```

That will print the document ID, in this case `1240`.

## Tools

### Downloader

Currently the only implemented tool is a downloader, `download.py`. If provided an ICC document ID, it will go through the table of contents for the document and download all the sections at a reasonable rate, stopping if an error is encountered.

For example, to download the current North Carolina state building code, you can do:

```bash
./download.py 1240
```

The API responses received will be saved in `./api/`, for later perusal and to allow offline development of other tools. You can move this directory with the `--base-directory` option.

The actual content is split across many responses, each of which is a quoted JSON string containing HTML-like XML, which may be intended to be part of an ePUB document. Because this is very unwieldy, the downloader tool has a `--combined-document` option, which can be used to additionally save an HTML file of the entire document strung together:

```bash
./download.py 1240 --combined-document code.html
```

The resulting HTML file (in this case, `code.html`), can be opened with a normal web browser for offline viewing (for example, at a job site where Internet access is unreliable).

### Online Viewer

It is desirable to provide an on-demand viewer, which would be a more direct substitute for ICC's viewer application, and which would not need to cache the entire document first. However, this has not been implemented yet. 

## Legal Notes
ICC-hosted building codes are likely to contain large portions of the IBC, which is subject to copyright. ICC makes many building codes available to the public without authentication, but seems to assume most people will choose to use the web-based viewer they have written, rather than accessing their API. Although the API is open to the public Internet, and one might assume that an organization publishing a document they wrote via HTTP extends an implied license to the receiver of that document to actually receive and review it using their user agent, ICC might see the situation differently. People who deal with laws and regulations [do not always understand computers](https://www.theverge.com/2021/12/31/22861188/missouri-governor-mike-parson-hack-website-source-code) or the concept and [fiduciary duties](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3827421) of a "user agent".

ICC may intend terms of use to apply to their API that would prohibit the use of these tools. A person accessing the API, or accessing the ICC web site, may or may not be legally bound by these terms. [It may or may not be legal to send requests to the API without agreeing to those terms.](https://techcrunch.com/2021/06/14/supreme-court-revives-linkedin-bid-to-protect-user-data-from-web-scrapers/) If I was a lawyer I wouldn't be writing Python scripts to help me view the laws because I would know all the laws already.
