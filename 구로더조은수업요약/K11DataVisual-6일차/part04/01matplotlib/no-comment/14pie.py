# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('../data/auto-mpg.csv', header=None)

plt.style.use('default')   

df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

df['count'] = 1
df_origin = df.groupby('origin').sum()
print(df_origin.head())

df_origin.index = ['USA', 'EU', 'JAPAN']

df_origin['count'].plot(kind='pie', 
                     figsize=(7, 5),
                     autopct='%1.2f%%',
                     startangle=10,
                     colors=['chocolate', 'bisque', 'cadetblue']
                     )
plt.title('Model Origin', size=20)
plt.axis('equal')
plt.legend(labels=df_origin.index, loc='upper right')
plt.show()
