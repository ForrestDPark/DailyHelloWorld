# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt

'''
산점도(Scatter plot)
: 연속되는 값을 갖는 서로 다른 두 변수 사이의 관계를 나타낸다. 
x, y축에 변수를 두고 데이터가 위치한 좌표를 찾아 점으로 표시한다. 
'''
plt.style.use('default')

df = pd.read_csv('../data/auto-mpg.csv', header=None)

df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']
'''
x : x축은 자동차의 무게로 설정한다. 
y : y축은 연비로 설정한다. 
s : 점의 크기를 설정한다.  
차가 무거울수록 연비는 떨어지므로 반비례하는 성향을 보인다. 
'''
df.plot(kind='scatter', x='weight', y='mpg', c='blue', s=10, figsize=(10,5))
plt.title('Scatter Plot - mpg vs weight')
plt.show()
