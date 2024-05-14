from flask import Flask, request, render_template
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from configparser import ConfigParser
import random
import string
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import os

app = Flask(__name__)

# Load configuration
config = ConfigParser()
config.read('config.ini')

# Email configuration
SMTP_SERVER = config.get('EMAIL', 'SMTP_SERVER')
SMTP_PORT = config.getint('EMAIL', 'SMTP_PORT')
SENDER_EMAIL = config.get('EMAIL', 'SENDER_EMAIL')
SENDER_PASSWORD = config.get('EMAIL', 'SENDER_PASSWORD')

# List of user agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.100 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.121 Safari/537.36'
]

def generate_random_number():
    return ''.join(random.choices(string.digits, k=6))

def get_content(url, use_selenium=False):
    user_agent = random.choice(USER_AGENTS)
    if use_selenium:
        return get_full_page_content_selenium(url, user_agent)
    else:
        headers = {'User-Agent': user_agent}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text

def get_full_page_content_selenium(url, user_agent):
    service = Service(ChromeDriverManager().install())
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f"user-agent={user_agent}")
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    except TimeoutException:
        print("Timed out waiting for page to load")
    content = driver.page_source
    driver.quit()
    return content

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup(["script", "style", "header", "footer", "nav", "form"]):
        element.decompose()
    text = ' '.join(soup.stripped_strings)
    return text

def check_webpage_content(url, search_terms, use_selenium=False):
    try:
        html_content = get_content(url, use_selenium)
        text_content = clean_html(html_content).lower()
        print(f"Checking Link: {url}")
        all_found = all(term.lower() in text_content for term in search_terms)
        print(f"Content Found: {'True' if all_found else 'False'}")
        return all_found
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error for {url}: {e}")
        return False
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return False

def api_search(query, engine, api_details):
    if engine.lower() == "google":
        url = "https://www.googleapis.com/customsearch/v1"
        params = {'key': api_details['api_key'], 'cx': api_details['cse_id'], 'q': query}
    elif engine.lower() == "bing":
        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {'Ocp-Apim-Subscription-Key': api_details['api_key']}
        params = {'q': query}
    response = requests.get(url, headers=headers if engine.lower() == "bing" else {}, params=params)
    response.raise_for_status()
    if engine.lower() == "google":
        return [item['link'] for item in response.json().get('items', [])]
    elif engine.lower() == "bing":
        return [item['url'] for item in response.json().get('webPages', {}).get('value', [])]

def search_and_check(name, name_variations, keywords, api_details):
    results = defaultdict(lambda: defaultdict(list))
    for engine in ["google", "bing"]:
        for variation in [name] + name_variations:
            for keyword in keywords:
                query = f"{variation} {keyword}".strip()
                links = api_search(query, engine, api_details[engine])
                for link in links:
                    domain = link.split('/')[2]
                    use_selenium = 'liverpoolecho.co.uk' in link  # Example domain that needs Selenium
                    if check_webpage_content(link, [variation, keyword], use_selenium):
                        results[engine][domain].append(link)
    return results

def save_results(client_name, results):
    base_dir = Path(client_name)
    base_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    file_path = base_dir / f"{client_name}_{timestamp}.txt"
    with open(file_path, 'w') as file:
        for engine, domains in results.items():
            file.write(f"{engine} Results:\n")
            for domain, links in domains.items():
                file.write(f"\nDomain: {domain}\n")
                for link in links:
                    file.write(f"  - {link}\n")
                file.write("\n")

    return file_path

def send_email(subject, body, recipient_email):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    client_name = request.form['client_name']
    name_variations = request.form['name_variations'].split(',')
    keywords = request.form['keywords'].split(',')
    recipient_email = request.form['recipient_email']

    api_details = {
        'google': {
            'api_key': config.get('API_KEYS', 'GOOGLE_API_KEY'),
            'cse_id': config.get('API_KEYS', 'GOOGLE_CSE_ID')
        },
        'bing': {
            'api_key': config.get('API_KEYS', 'BING_API_KEY')
        }
    }

    def run_search():
        results = search_and_check(client_name, name_variations, keywords, api_details)
        file_path = save_results(client_name, results)
        random_number = generate_random_number()

        email_body = f"[EXECUTION OF SCRIPT REPORT]\n\n" \
                     f"Time of Execution: {datetime.now().strftime('%H:%M:%S')}\n" \
                     f"Date of Execution: {datetime.now().strftime('%Y-%m-%d')}\n\n" \
                     f"Ticket Number (for IT Purposes): {random_number}\n\n" \
                     f"Search Terms Used: {' '.join([client_name] + keywords)}\n\n" \
                     f"Results Output:\n{open(file_path).read()}\n\n" \
                     f"Bing API Key: {api_details['bing']['api_key']}\n" \
                     f"Google API Key: {api_details['google']['api_key']}\n" \
                     f"Google CSE Key: {api_details['google']['cse_id']}"

        send_email(f"Search Results for {client_name}", email_body, recipient_email)

    threading.Thread(target=run_search).start()
    return "Search started!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
