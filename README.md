
# Earnings Call Transcript Downloader

This project is a script that searches for and downloads earnings call transcripts for specific companies, validates them using OCR and AI, and renames them based on the fiscal quarter and year.

## Features

- Searches Google for earnings call transcripts of companies in PDF format.
- Downloads the PDFs, validates them using extracted text and Groq AI API.
- Renames files based on the company name, quarter, and fiscal year.
- Handles SSL errors and retries downloads automatically.

## Setup

### Requirements
- Python 3.7+
- See `requirements.txt` for all dependencies.

### Installation
1. Clone this repository:
   ```bash
   git clone https://github.com/tejatan/EarningCall.git
   cd EarningCall


2. Create a virtual environment and activate it:
    python -m venv venv
    source venv/bin/activate   # On Windows use `venv\Scripts\activate`

3. Install the dependencies:
    pip install -r requirements.txt


Usage
To run the script:

    python main.py
    Ensure that you replace 'Your_key_here' in main.py with your actual API keys.
    Ensure to add company ticker and company name 






Not optimized for all companies, it may even fail for the example company based on the model used, be cautious of the pdf downloaded and API key usage. Use with caution. and verify data every now and then so you can continue to analyze with no problem. 

Problems: Optimize for every company as needed

