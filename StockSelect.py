#---------------------------------------------
# Title:    Stock Trading Algorithm 
# Prog:     Select the Stocks
# Author:   Jack Elkes
# Date:     27SEP2021
#---------------------------------------------

import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

URL = "https://uk.finance.yahoo.com/most-active"
page = requests.get(URL)

soup = BeautifulSoup(page.content, 'lxml')
most_acive = soup.select('table td')

# Things to Search
stock1 = soup.find('a', attrs={"data-reactid": "79" }).get_text() 
stock2 = soup.find('a', attrs={"data-reactid": "111"}).get_text()
stock3 = soup.find('a', attrs={"data-reactid": "143"}).get_text()  
stock4 = soup.find('a', attrs={"data-reactid": "175"}).get_text() 
stock5 = soup.find('a', attrs={"data-reactid": "207"}).get_text() 

#print(most_acive)
#print(stock1, stock2, stock3, stock4, stock4)

# --------------------------------------------------------------
# Using yFinance package
# --------------------------------------------------------------

# Take Todays date and 7 days ago as Start & Finish for Stock High/Low
today = datetime.now()
today = today.date()
week = today - timedelta(days=7)

for i in range(1, 6):
    exec(f"yf{i} = yf.Ticker(stock{i})")
    exec(f"hist{i} = yf{i}.history(start=week,  end=today)")
    exec(f"hist{i}.low = hist{i}['Low'].min()")
    exec(f"hist{i}.high = hist{i}['High'].max()")