# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
조건을 적용하여 화면을 그리드로 분할하기
: 행, 열방향으로 서로 다른 조건을 적용하여 여러개의 서브플롯(그래프)를
만든다. 열방향으로 who(탑승객구분), 행방향으로 survived(생존여부)으로
구분한다. 
'''

titanic = sns.load_dataset('titanic')
 
sns.set_style('whitegrid')

g = sns.FacetGrid(data=titanic, col='who', row='survived') 

g = g.map(plt.hist, 'age')

