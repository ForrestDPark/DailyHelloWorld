# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
df = pd.read_excel('../data/시도별 전출입 인구수.xlsx', 
                   engine='openpyxl', header=0)
print(df.head())

df = df.fillna(method='ffill')
print(df.head())

mask = (df['전출지별']=='서울특별시') & (df['전입지별']!='서울특별시')
df_seoul = df[mask]
print(df_seoul)
df_seoul = df_seoul.drop(['전출지별'], axis=1)
print(df_seoul)
df_seoul.rename({'전입지별':'전입지'}, axis=1, inplace=True)
print(df_seoul)
df_seoul.set_index('전입지', inplace=True)
print(df_seoul)
sr_one = df_seoul.loc['경기도']
print(sr_one)

plt.plot(sr_one.index, sr_one.values)

plt.title('서울 -> 경기 인구 이동')
plt.xlabel('기간')
plt.ylabel('이동 인구수')

plt.show()
