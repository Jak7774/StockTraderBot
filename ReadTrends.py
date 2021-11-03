
#---------------------------------------------
# Title:    Stock Trading Algorithm 
# Prog:     Read Trends
# Author:   Jack Elkes
# Date:     27SEP2021
#---------------------------------------------

import Sensitive
import pandas as pd
import matplotlib.pyplot as plt
from alpha_vantage.timeseries import TimeSeries
from StockSelect import * # Import Stocks

#key = open('API_Ket.txt').read() ## Use if want to hide key in Text File
key = 

# Call to get data (split out meta)
ts = TimeSeries(key, output_format = 'pandas')
data, meta = ts.get_intraday("GOOGL", interval = '1min', outputsize = 'full')

# Rename Columns
col = ['open', 'high', 'low', 'close', 'volume']
data.columns = col

# Format Date and Time only Columns
data['TradeDate'] = data.index.date
data['time'] = data.index.time

# Create Var with only trading within normal hours
market = data.between_time('09:30:00', '16:00:00').copy()
market.sort_index(inplace=True)

# Aggregate Highs & Lows for last 7 days 
day_agg = market.groupby('TradeDate').agg({'low':min, 'high':max}) # by Day
lows = market.loc[market.groupby('TradeDate')['low'].idxmin()]['low']
highs = market.loc[market.groupby('TradeDate')['high'].idxmax()]['high']
lowest = lows.min()
highest = highs.max()

print(lows, highs)
print(highest, lowest)

# plt.plot(day_agg['low'], label='Low')
# plt.plot(day_agg['high'], label='High')
# plt.legend(loc=2)
# plt.show()

