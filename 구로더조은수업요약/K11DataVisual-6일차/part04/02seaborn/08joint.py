# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
조인트 그래프
    : 산점도를 기본으로 표시하고, x-y축의 각 변수에 대한 히스토그램을
    동시에 보여주므로, 두 변수의 관계와 데이터가 분산되어 있는 정도를 
    파악하기좋다.
'''
titanic = sns.load_dataset('titanic')
 
sns.set_style('whitegrid')

'''
kind='reg' : 회귀선 추가
kind='hex' : 육각 산점도
kind='kde' : 커널 밀집 그래프
'''
j1 = sns.jointplot(x='fare', y='age', data=titanic) 
j2 = sns.jointplot(x='fare', y='age', kind='reg', data=titanic) 
j3 = sns.jointplot(x='fare', y='age', kind='hex', data=titanic) 
j4 = sns.jointplot(x='fare', y='age', kind='kde', data=titanic) 

j1.fig.suptitle('titanic fare - scatter', size=15)
j2.fig.suptitle('titanic fare - reg', size=15)
j3.fig.suptitle('titanic fare - hex', size=15)
j4.fig.suptitle('titanic fare - kde', size=15)

plt.show()

