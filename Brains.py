#---------------------------------------------
# Title:    Stock Trading Algorithm 
# Author:   Jack Elkes
# Date:     27SEP2021
#---------------------------------------------

# This will be the file for the logic the  bot will use to make trades

import numpy as np
import sklearn.linear_model as LinearRegression
import ReadTrends as RT

#----------------------------------------
# Find current value 
#----------------------------------------

current_value = 2500

#----------------------------------------
# Buy or Sell? 
#----------------------------------------

if current_value >= RT.highest:
    buy = 0
elif current_value < RT.lowest:
    buy = 1

y1 = np.array(RT.day_agg["low"])
y2 = np.array(RT.day_agg["high"])
x = np.arange(y1.shape[0])
x = np.array(x).reshape(-1,1)

model = LinearRegression.LinearRegression()
model.fit(x, y1)
print(model.coef_)
