# -*- coding: utf-8 -*-

import pandas as pd
import matplotlib.pyplot as plt

plt.style.use('classic')
df = pd.read_csv('../data/auto-mpg.csv', header=None)
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

df['mpg'].plot(kind='hist', bins=10, color='coral', figsize=(10,5))

plt.title('Histogram')
plt.xlabel('mpg')
plt.show()
