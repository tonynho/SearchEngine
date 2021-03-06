import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from sqlalchemy.orm import Session
from connection import Base
from connection import engine
from page import Page
from website import Website

from queue import Queue


class WebCrawler:
    PAGE_COUNTER = 0
    CURR_WEBSITE_ID = 0

    def __init__(self, domain):
        self.domain = domain
        self.scanned_urls = []
        self.queue = Queue()

        Base.metadata.create_all(engine)
        self.session = Session(bind=engine)

    def is_outgoing(self, url):
        if self.domain not in url:
            return True

        if url.startswith('https://', 0, 8):
            url = url[8:]
        else:
            url = url[7:]       # http://

        if url.startswith('www.'):
            url = url[4:]

        if url.startswith(self.domain) and '#' not in url:
            return False

        return True

    def prepare_link(self, url, href):
        return urljoin(url, href)

    def scan_page(self, url):
        if url in self.scanned_urls:
            return

        print(url)
        self.scanned_urls.append(url)

        r = requests.get(url)
        if r.status_code != 200:
            return
        soup = BeautifulSoup(r.text)

        self.save_page_db(url, soup)

        self.PAGE_COUNTER += 1

        for link in soup.find_all('a'):
            href = link.get('href')
            new_link = self.prepare_link(url, href)
            if not self.is_outgoing(new_link):
                self.queue.put(new_link)

    def start_scanning(self, url):
        self.queue.put(url)
        print("Start while")

        while not self.queue.empty():
            temp_url = self.queue.get()

            self.scan_page(temp_url)    # scan, save, increment, fill queue

    def scan_website(self, url):
        url = 'http://' + self.domain

        if self.is_domain_crawled(self.domain):
            return

        r = requests.get(url)
        if r.status_code != 200:
            return
        soup = BeautifulSoup(r.text)

        if self.get_page_title(soup) == '':     # skip pages without name
            return

        self.CURR_WEBSITE_ID = 1 + self.get_last_website_id()

        self.start_scanning(url)    # crawl pages to get pages_count
        pages_count = self.PAGE_COUNTER
        self.PAGE_COUNTER = 0

        self.save_website_db(url, soup, pages_count)
        self.assign_scores_to_website_pages(self.CURR_WEBSITE_ID)

    def save_website_db(self, url, soup, pages_count):
        args = {
            'url': url,
            'title': self.get_page_title(soup),
            'domain': self.domain,
            'pages_count': pages_count,
            'is_html_5': self.is_html_5(soup)
        }
        self.session.add(Website(**args))
        self.session.commit()

    def save_page_db(self, url, soup):
        args = {
            'url': url,
            'title': self.get_page_title(soup),
            'desc': self.get_page_description(soup),
            'lines_count': self.count_lines(soup),
            'images_count': self.count_images(soup),
            'score': 0,
            'website_id': self.CURR_WEBSITE_ID
        }
        self.session.add(Page(**args))
        self.session.commit()

    def get_last_website_id(self):
        websites = self.session.query(Website).all()
        return len(websites)

    def is_domain_crawled(self, domain):
        result = self.session.query(Website).\
            filter(Website.domain == domain).all()
        return True if len(result) > 0 else False

    def get_page_title(self, soup):
        title = soup.find('meta', {'property': 'og:title'})
        if title is None:
            title = soup.title
            return '' if title is None else title.string
        else:
            return title['content']

    def get_page_description(self, soup):
        desc = soup.find('meta', {'property': 'og:description'})
        if desc is None:
            desc = soup.find('meta', {'name': 'description'})
            return '' if desc is None else desc['content']
        else:
            return desc['content']

    def is_server_ssl(self, url):
        try:
            req = requests.get(url, verify=True)
        except Exception:
            return False
        return True if req.status_code == 200 else False

    def is_html_5(self, soup):
        html = soup.prettify()
        if html.find('<!DOCTYPE doctype html>') != -1 or \
           html.find('<!DOCTYPE html>') != -1:
            return True
        return False

    def count_lines(self, soup):
        if len(soup('body')) == 0:      # skip files
            return

        for script in soup(['script', 'style']):
            script.extract()

        text = soup.get_text()
        lines = [line for line in text.splitlines() if len(line.strip()) > 1]
        return len(lines)

    def count_images(self, soup):
        return len(soup(['img']))

    def calculate_page_score(self, page):
        score = 0
        if page.title != '':
            score += 10
        if page.desc != '':
            score += 10
        if page.website.is_html_5:
            score += 10
        score += 4 * (page.website.pages_count // 50)
        score += 5 * (page.lines_count // 50)
        score += 2 * page.images_count

        return score

    def assign_scores_to_website_pages(self, id):
        pages = self.session.query(Page).filter(Page.website_id == id).all()

        for page in pages:
            page.score = self.calculate_page_score(page)

        self.session.commit()


def main():
    crawler = WebCrawler('hackbulgaria.com')
    crawler.scan_website('http://hackbulgaria.com/')


if __name__ == '__main__':
    main()
