#!/usr/bin/env python3

from bs4 import BeautifulSoup
import requests
import os
import hashlib
from urllib.parse import urlparse
import re
import shutil
import json
import argparse


def compute_image_path(url_path, root):
    m = hashlib.sha256()
    m.update(url_path.encode('utf-8'))
    os.makedirs(os.path.join(root, ".cached"), exist_ok=True)

    u_path = urlparse(url_path)
    output_path = u_path.path
    output_path = os.path.splitext(output_path)
    image_name = f'{m.hexdigest()}{output_path[1]}'
    file_path = os.path.join(root, "images", image_name)
    return file_path, image_name


def download_image(url_path, root):
    image_path, image_name = compute_image_path(url_path, root)
    if os.path.exists(image_path):
        return image_name
    else:
        headers = {
            'Accept': '*/*',
            'User-Agent': 'curl/7.64.1',
        }
        req = requests.get(url_path, headers=headers, stream=True)
        if req.status_code != 200:
            print(f'Cannot make request. Result: {req.status_code:d}')
            exit(1)

        with open(image_path, 'wb') as file_out:
            req.raw.decode_content = True
            shutil.copyfileobj(req.raw, file_out)

        return image_name


def load_file_content(url_path, file_path):
    if os.path.exists(file_path):
        with open(file_path, 'rt') as file_in:
            content = file_in.read()
    else:
        headers = {
            'Accept': '*/*',
            'User-Agent': 'curl/7.64.1',
        }
        req = requests.get(url_path, headers=headers)
        if req.status_code != 200:
            print(f'Cannot make request. Result: {req.status_code:d}')
            exit(1)

        with open(file_path, 'wt') as file_out:
            file_out.write(req.text)

        content = req.text
    return content


def remove_tag(site, tag, attrs):
    b = site.find(tag, attrs=attrs)
    if b is not None:
        b.extract()


class Renderer(object):
    def render_tag_p(self, file_out, tag):
        file_out.write(tag.text)
        file_out.write('\n\n')

    def render_tag_h1(self, file_out, tag):
        file_out.write(f'=== {tag.string}\n\n')

    def render_tag_h2(self, file_out, tag):
        file_out.write(f'=== {tag.string}\n\n')

    def render_tag_h3(self, file_out, tag):
        file_out.write(f'==== {tag.string}\n\n')

    def render_tag_h4(self, file_out, tag):
        file_out.write(f'===== {tag.string}\n\n')

    def render_tag_ul(self, file_out, tag):
        for li in tag:
            if li.name != 'li':
                continue
            file_out.write(f'- {li.text}\n')
        file_out.write('\n\n')

    def render_tag_ol(self, file_out, tag):
        for li in tag:
            if li.name != 'li':
                continue
            file_out.write(f'* {li.text}\n')
        file_out.write('\n\n')

    def render_tag_div(self, file_out, div):
        self.render_tags(file_out, div)

    def render_tag_blockquote(self, file_out, tag):
        file_out.write('[quote]\n')
        file_out.write('____\n')
        self.render_tags(file_out, tag)
        file_out.write('____\n')

    def render_tag_table(self, file_out, tag):
        file_out.write('++++\n')
        file_out.write(tag.prettify())
        file_out.write('++++\n')

    def render_tag_pre(self, file_out, tag):
        code_pattern = r"^\[code\s+lang=(?P<lang>.*)\](?P<content>.*)\[\/code\]$"
        matches = re.finditer(code_pattern, tag.text, re.MULTILINE | re.DOTALL)

        for matchNum, match in enumerate(matches, start=1):
            ascii_content = f'''[source, {match.group('lang')}]
----
{match.group('content')}
----
'''
            file_out.write(ascii_content)

        if matches is None:
            file_out.write(f'''[listing]
....
{tag.text}
....

''')

    def render_tags(self, file_out, site):
        handlers = {
            'p': self.render_tag_p,
            'h1': self.render_tag_h1,
            'h2': self.render_tag_h2,
            'h3': self.render_tag_h3,
            'h4': self.render_tag_h4,
            'ul': self.render_tag_ul,
            'ol': self.render_tag_ol,
            'div': self.render_tag_div,
            'blockquote': self.render_tag_blockquote,
            'figure': self.render_tag_p,
            'table': self.render_tag_table,
            'pre': self.render_tag_pre,
        }
        for tag in site:
            if tag.name is None:
                continue
            if tag.name in handlers:
                handlers[tag.name](file_out, tag)
            else:
                print('=============')
                print(tag)


class UntoolsRenderer(Renderer):
    def render_tag_div(self, file_out, div):
        file_out.write(div.text)
        file_out.write('\n\n')


class Transformer(object):
    def __init__(self, config, doc, site):
        self.config = config
        self.doc = doc
        self.site = site

    def transform_strong(self):
        for a in self.site.find_all(['strong', 'b']):
            text = a.text
            a.replace_with(f'**{text}**')

    def transform_italic(self):
        for a in self.site.find_all(['italic', 'i', 'em']):
            text = a.text
            a.replace_with(f'__{text}__')

    def transform_a(self):
        for a in self.site.find_all('a'):
            href = a['href']
            text = a.text
            a.replace_with(f'link:{href}[{text}]')

    def transform_img(self):
        for img in self.site.find_all('img'):
            alt = img['alt']
            height = img.get('height', '')
            width = img.get('width', '')
            src = img['src']
            srcset = img.get('srcset', None)
            if srcset is not None:
                srcs = srcset.split(',')
                imgs = {}
                for s in srcs:
                    ss = s.strip().split(' ')
                    imgs[ss[1]] = ss[0]
                largest = sorted(imgs.keys())[0]
                src = imgs[largest]
                if 'w' in largest:
                    width = largest.replace('w', '')
                if 'h' in largest:
                    height = largest.replace('h', '')
            url_path = requests.compat.urljoin(self.config['src_url'], src)
            image_name = download_image(url_path, self.config['output_dir'])
            repl = f'image:{image_name}[{alt},{width},{height}]'
            img.replace_with(repl)

    def transform(self):
        self.transform_strong()
        self.transform_italic()
        self.transform_img()
        self.transform_a()


class UntoolsTransformer(Transformer):
    def transform_h2(self):
        for a in self.site.find_all('h2'):
            text = a.text
            repl = f'=== {text}\n\n'
            p = self.doc.new_tag('p')
            p.string = repl
            a.replace_with(p)

    def transform_h3(self):
        for a in self.site.find_all('h3'):
            text = a.text
            repl = f'==== {text}\n\n'
            p = self.doc.new_tag('p')
            p.string = repl
            a.replace_with(p)

    def transform_sources(self):
        source = self.site.find('div', class_=re.compile('article-module--sources--'))
        source.unwrap()

    def transform(self):
        self.transform_strong()
        self.transform_italic()
        self.transform_img()
        self.transform_a()
        # self.transform_h2()
        # self.transform_h3()
        self.transform_sources()


class Extractor(object):
    def __init__(self, bs):
        self.bs = bs
        self.site = None
        self.content = None

    def get_title(self):
        pass

    def get_published(self):
        time_published = self.bs.find('time', attrs={'class': 'entry-date published'})
        if time_published is not None:
            published = time_published.text
            return published
        else:
            return None

    def get_metadata(self):
        return ''

    def cleanup(self):
        remove_tag(self.site, 'div', attrs={'class': 'site-branding'})
        remove_tag(self.site, 'div', attrs={'class': 'navigation-top'})
        remove_tag(self.site, 'footer', attrs={'class': 'site-footer'})
        remove_tag(self.site, 'div', attrs={'class': 'searchsettings'})
        remove_tag(self.site, 'section', attrs={'id': 'ajaxsearchlitewidget-2'})
        remove_tag(self.site, 'aside', attrs={'id': 'secondary'})
        remove_tag(self.site, 'nav', attrs={'class': 'post-navigation'})
        remove_tag(self.site, 'header', attrs={'id': 'masthead'})

    def get_content(self):
        return self.site


class Untools(Extractor):
    def get_title(self):
        import re
        header = self.bs.find('div', class_=re.compile('article-module--top--'))
        title = header.find('h2').text
        return title

    def get_metadata(self):
        import re
        header = self.bs.find('div', class_=re.compile('article-module--top--'))
        tag = header.find('span', class_=re.compile('tag-module--tag--')).text
        usage = header.find('div', class_=re.compile('article-module--when-useful--')).text

        return f'.{tag}\n****\n{usage}\n****\n\n'

    def cleanup(self):
        self.site = self.bs.find(class_=re.compile('article-module--content--'))
        super(Untools, self).cleanup()


class UnintendedConsequences(Extractor):
    def get_title(self):
        return self.bs.find('h1').text

    def cleanup(self):
        self.site = self.bs.find(id='page')
        super(UnintendedConsequences, self).cleanup()

    def get_content(self):
        return self.site.find(attrs={'class': 'entry-content'})


class TheMorningPaperExtractor(Extractor):
    def get_title(self):
        header = self.bs.find('h1', class_='entry-title')
        return header.text

    def cleanup(self):
        self.site = self.bs.find('div', class_='entry-content')
        super(TheMorningPaperExtractor, self).cleanup()


def create_extractor(url_path, bs):
    if 'untools.co' in url_path:
        return Untools(bs)
    if 'unintendedconsequenc' in url_path:
        return UnintendedConsequences(bs)
    if 'blog.acolyer.org' in url_path:
        return TheMorningPaperExtractor(bs)
    return Extractor(bs)


def create_transformer(url_path, bs, content, root):
    config = {
        "src_url": url_path,
        "output_dir": root
    }
    if 'untools.co' in url_path:
        return UntoolsTransformer(config, bs, content)
    if 'unintendedconsequenc' in url_path:
        return Transformer(config, bs, content)
    if 'blog.acolyer.org' in url_path:
        return Transformer(config, bs, content)
    return Transformer(config, bs, content)


def create_renderer(url_path):
    if 'untools.co' in url_path:
        return UntoolsRenderer()
    if 'unintendedconsequenc' in url_path:
        return Renderer()
    if 'blog.acolyer.org' in url_path:
        return Renderer()
    return Renderer()


def download_content(url_path, root):
    m = hashlib.sha256()
    m.update(url_path.encode('utf-8'))
    file_path = os.path.join(root, ".cached", "%s.html" % m.hexdigest())
    output_path = urlparse(url_path).path
    output_path = output_path.rstrip('/')
    output_path = os.path.join(root, os.path.basename(output_path))
    os.makedirs(output_path, exist_ok=True)
    output_path = os.path.join(output_path, 'index.asciidoc')
    print(output_path)

    content = load_file_content(url_path, file_path)
    bs = BeautifulSoup(content, 'html.parser')

    with open(output_path, 'w') as a_out:
        extractor = create_extractor(url_path, bs)
        a_out.write(f'== {extractor.get_title()}\n\n')

        time_published = extractor.get_published()
        if time_published is not None:
            published_info = f'published on {time_published}'
        else:
            published_info = ''
        article_metadata = f'link:{url_path}[original article] {published_info}\n\n{extractor.get_metadata()}'
        a_out.write(article_metadata)

        extractor.cleanup()
        transformer = create_transformer(url_path, bs, extractor.get_content(), root)
        transformer.transform()
        renderer = create_renderer(url_path)
        renderer.render_tags(a_out, extractor.get_content())
    return output_path


def read_configuration(file_path):
    with open(file_path, 'r') as file_in:
        data = json.load(file_in)
        return data


def generate_new_configuration(file_path):
    template = {
            "title": "__fill the title__",
            "author": "__fill the author__",
            "version": "v1.0",
            "homepage": "__fill url to home page__",
            "output_dir": "__fill output dir__",
            "urls": [
            ]
        }
    with open(file_path, 'w') as file_out:
        json.dump(template, file_out, indent=4)


def generate_makefile(output_dir):
    template = '''html:
\tasciidoctor index.asciidoc -d book -b html5 -D output
\tcp -r images output/

epub:
\tasciidoctor-epub3 index.asciidoc -d book -D output
'''
    file_path = os.path.join(output_dir, 'Makefile')
    with open(file_path, 'w') as out_file:
        out_file.write(template)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--new', '-n', type=bool, default=False,
                        help='Generate new configuration file. '
                             'File name will be specified in the --input parameter')
    parser.add_argument('--input', '-i', type=str, help='Configuration file')
    args = parser.parse_args()
    if args.new:
        generate_new_configuration(args.input)
        exit(0)

    config = read_configuration(args.input)
    paths = config['urls']
    root = config['output_dir']
    os.makedirs(os.path.join(root, ".cached"), exist_ok=True)
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    generate_makefile(root)

    files = []
    for url_path in paths:
        output_path = download_content(url_path, root)
        output_path = re.sub(f'^{root}/', '', output_path)
        files.append(output_path)

    included_files = '\n'.join(['include::%s[]' % x for x in files])
    content = f'''= {config["title"]}
{config["author"]}
{config["version"]}
:toc:
:imagesdir: images
:homepage: {config["homepage"]}

{included_files}
'''
    with open(os.path.join(root, 'index.asciidoc'), 'w') as index_file:
        index_file.write(content)


if __name__ == '__main__':
    main()
