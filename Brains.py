#---------------------------------------------
# Title:    Stock Trading Algorithm 
# Author:   Jack Elkes
# Date:     27SEP2021
#---------------------------------------------

# This will be the file for the logic the  bot will use to make trades

import StockSelect as stock
import numpy as np
import sklearn.linear_model as LinearRegression
import ReadTrends as RT
from TradeLogs import * 
import datetime
import json

#----------------------------------------
# Find current value 
#----------------------------------------

current_value = 5000

#----------------------------------------
# Buy or Sell? 
#----------------------------------------

y1 = np.array(RT.day_agg["low"])
y2 = np.array(RT.day_agg["high"])
x = np.arange(y1.shape[0])
x = np.array(x).reshape(-1,1)

model = LinearRegression.LinearRegression()
model.fit(x, y1)
print(model.coef_)

y_pred = model.predict(x)
trade = ""

if y_pred[0] > 0 and current_value <= RT.highest:
    print("you should buy")
    trade = "Buy"
if y_pred[0] < 0 and current_value > RT.highest:
    print("you should sell")
    trade = "Sell"
elif current_value < RT.lowest:
    print("you should sell")
    trade = "Sell"
else:
    trade = "Not Sure"

with open('trades.txt', 'w') as outfile:
    json.dump(trades, outfile, indent=4, sort_keys=False)
