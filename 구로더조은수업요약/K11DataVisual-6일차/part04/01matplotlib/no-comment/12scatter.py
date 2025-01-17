# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt

plt.style.use('default')

df = pd.read_csv('../data/auto-mpg.csv', header=None)

df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

df.plot(kind='scatter', x='weight', y='mpg', c='blue', s=10, figsize=(10,5))
plt.title('Scatter Plot - mpg vs weight')
plt.show()
