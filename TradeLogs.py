#---------------------------------------------
# Title:    Stock Trading Algorithm 
# Author:   Jack Elkes
# Date:     27SEP2021
#---------------------------------------------

day = datetime.date.today().strftime("%d%b%Y")
current_time = datetime.datetime.now().time().strftime("%H:%M:%S")

trades = {}
trades[day] = []

# --- For Each Stock, Create 
Stock1 = { 'StockName': stock.stock1}
Stock2 = { 'StockName': stock.stock2}
Stock3 = { 'StockName': stock.stock3}
Stock4 = { 'StockName': stock.stock4}
Stock5 = { 'StockName': stock.stock5}

Stock1Trades = {}
Stock2Trades = {}
Stock3Trades = {}
Stock4Trades = {}
Stock5Trades = {}

def LogTrade(stockname, stockitem, tradenum):
    stockitem['TradeNo.'] = tradenum
    stockitem['Price'] = current_value
    stockitem['Time'] = current_time
    stockitem['Decision'] = trade

    trades[day] = stockname
    stockname['Trades'] = stockitem