# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt

'''
히스토그램
: 변수가 하나인 단변수 데이터의 빈도수를 그래프로 표현한것이다. 
x축을 같은 크기의 여러 구간으로 나누고 각 구간에 속하는 데이터값의
갯수를 y축에 표시한다. 
'''
#그래프의 스타일 지정
plt.style.use('classic')
#header옵션이 none이므로 전체데이터를 읽어서 데이터프레임으로 만든다.
df = pd.read_csv('../data/auto-mpg.csv', header=None)
#각 열의 이름을 지정한다. 연비, 실린더 .. 등으로 구성된다. 
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']
'''
히스토그램을 그린다. 
bins옵션으로 10개의 구간으로 나눈다. 수치가 커지면 그래프의 폭이 좁아진다.
즉 좀더 세분화할 수 있다.  
'''
df['mpg'].plot(kind='hist', bins=10, color='coral', figsize=(10,5))

#타이틀과 라벨지정
plt.title('Histogram')
plt.xlabel('mpg')
plt.show()
