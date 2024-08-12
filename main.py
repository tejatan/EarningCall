import os
import re
import threading
import http.client
import json
import requests
import pdfplumber
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from groq import Groq
import urllib3
import os


# Directly setting the environment variables
os.environ['GROQ_API_KEY'] = 'Your_key_here'
os.environ['API_KEY'] = 'Your_key_here'


# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load API keys from environment variables
os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY')
API_KEY = os.getenv('API_KEY')
SEARCH_URL = "https://google.serper.dev/search"
TIMEOUT = 30  # 30 seconds timeout for each company

ticker_to_company = {
    # Define your tickers and company names here
    "ASIANPAINT.NS": "Asian Paints Limited",
    "AXISBANK.NS": "Axis Bank Limited",
    # Add the rest of the companies...
}


def search_earnings_call(company_name, year):
    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({
            "q": f"{company_name} earnings call transcript {year} filetype:pdf"
        })
        headers = {
            'X-API-KEY': API_KEY,
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        data = res.read()
        response_json = json.loads(data)
        print(f"API Response for {company_name} in {year}: {json.dumps(response_json, indent=4)}")
        return response_json
    except Exception as e:
        print(f"Error during search for {company_name} in {year}: {e}")
        return {}



def download_pdf(url, file_name, folder, company_name, download_event):
    os.makedirs(folder, exist_ok=True)

    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        response = session.get(url, verify=False)  # Disabling SSL verification
        file_path = os.path.join(folder, file_name)

        with open(file_path, 'wb') as file:
            file.write(response.content)
        print(f"Downloaded: {file_path}")

        # Validate and rename the downloaded file
        if not validate_and_rename_file_with_groq(file_path, company_name, folder, url):
            print(f"Validation failed: {file_path} does not match {company_name}. Deleting file.")
            os.remove(file_path)
            return

        download_event.set()
    except requests.exceptions.SSLError as e:
        print(f"SSL Error occurred while downloading {url}: {e}")
    except Exception as e:
        print(f"Error occurred while downloading {url}: {e}")


def validate_and_rename_file_with_groq(pdf_path, company_name, folder, url=None):
    try:
        text = extract_text_from_first_pages(pdf_path)
        if not text.strip():  # If no text was extracted, use OCR
            text = extract_text_with_ocr(pdf_path)

        # Send the extracted text to Groq for company name validation
        company_name_response = send_company_name_to_groq(text, company_name)
        print("Groq Company Name Response:", company_name_response)

        # Check if the response matches the company name in the dictionary
        if company_name_response.lower() not in [company_name.lower(), company_name.lower().replace("limited", "ltd")]:
            print(f"Validation failed: Document does not match {company_name}. Deleting file.")
            os.remove(pdf_path)
            return False

        # Extract and validate the quarter and fiscal year
        quarter_fy_response = send_quarter_fy_to_groq(text, url)
        print("Groq Quarter and FY Response:", quarter_fy_response)

        quarter, fyear = extract_quarter_fy_from_groq_response(quarter_fy_response)
        if quarter == "Unknown" or fyear == "Unknown":
            print(f"Could not determine quarter/fiscal year for {pdf_path}.")
            return False

        # Rename the file according to the validated company name, quarter, and fiscal year
        new_file_name = f"{company_name}_Q{quarter}_FY{fyear}.pdf"
        new_file_path = os.path.join(folder, new_file_name)

        # If the file already exists, overwrite it
        if os.path.exists(new_file_path):
            os.remove(new_file_path)

        os.rename(pdf_path, new_file_path)
        print(f"File renamed to: {new_file_name}")
        return True
    except Exception as e:
        print(f"Error during validation/renaming of {pdf_path}: {e}")
        return False


def extract_quarter_fy_from_groq_response(groq_response):
    quarter = "Unknown"
    fyear = "Unknown"

    # Define regex patterns for fiscal quarter and year
    quarter_pattern = re.compile(r"Q([1-4])", re.IGNORECASE)
    fyear_pattern = re.compile(r"FY[-\s]?(\d{2,4})", re.IGNORECASE)

    # Extract quarter
    quarter_match = quarter_pattern.search(groq_response)
    if quarter_match:
        quarter = quarter_match.group(1)

    # Extract fiscal year
    fyear_match = fyear_pattern.search(groq_response)
    if fyear_match:
        fyear = fyear_match.group(1)
        # Handle two-digit fiscal years (e.g., '18' should become '2018')
        if len(fyear) == 2:
            fyear = "20" + fyear

    return quarter, fyear


def extract_text_with_ocr(pdf_path):
    # Use docTR to extract text from PDF as a fallback
    doc = DocumentFile.from_pdf(pdf_path)
    model = ocr_predictor(pretrained=True)
    result = model(doc)

    extracted_text = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                line_text = ' '.join([word.value for word in line.words])
                extracted_text.append(line_text)

    return "\n".join(extracted_text)


def send_quarter_fy_to_groq(text, url=None):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    messages = [
        {
            "role": "user",
            "content": f"What is the fiscal quarter and fiscal year in the following document?\n\n{text}",
        }
    ]

    if url:
        messages.append(
            {
                "role": "user",
                "content": f"Based on the URL, the quarter and fiscal year might be included: {url}",
            }
        )

    chat_completion = client.chat.completions.create(
        messages=messages,
        model="llama3-8b-8192",
        temperature=0,
    )

    return chat_completion.choices[0].message.content


def send_company_name_to_groq(text, company_name):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    # Construct the message asking Groq to validate the company name
    messages = [
        {
            "role": "user",
            "content": f"Which company does the following document belong to? Please provide only the company name from the following list: {', '.join(ticker_to_company.values())}\n\n{text}",
        }
    ]

    chat_completion = client.chat.completions.create(
        messages=messages,
        model="llama3-8b-8192",
        temperature=0,
    )

    # Strip any extraneous whitespace or punctuation
    company_name_response = chat_completion.choices[0].message.content.strip()

    return company_name_response


def extract_text_from_first_pages(pdf_path, num_pages=2):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(min(num_pages, len(pdf.pages))):
            page = pdf.pages[i]
            text += page.extract_text() + "\n"
    return text


def process_search_results(company_name, ticker, search_results, download_event):
    if not search_results.get('organic'):
        print(f"No results found for {company_name} ({ticker})")
        return

    for result in search_results['organic']:
        link = result.get('link')
        title = result.get('title', '').lower()
        if link and link.endswith('.pdf'):
            file_name = f"{company_name}_temp.pdf"
            download_pdf(link, file_name, ticker, company_name, download_event)


def process_company(ticker, company_name, year):
    search_results = search_earnings_call(company_name, year)
    if not search_results.get('organic'):
        print(f"No results found for {company_name} ({ticker}) in {year}")
        return

    download_event = threading.Event()
    download_thread = threading.Thread(target=process_search_results,
                                       args=(company_name, ticker, search_results, download_event))
    download_thread.start()
    download_thread.join(TIMEOUT)

    if not download_event.is_set():
        print(f"No downloads for {year} {company_name} ({ticker}) in {TIMEOUT} seconds. Moving to next company.")
        return


def main():
    tickers = list(ticker_to_company.keys())
    years = range(2018, 2025)
    for ticker in tickers:
        company_name = ticker_to_company[ticker]
        for year in years:
            process_company(ticker, company_name, year)


if __name__ == "__main__":
    main()
