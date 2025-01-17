# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns
'''
이변수 데이터의 분포를 표현하기 위해 데이터프레임의 열(변수)을
두개씩 짝을 지어 표현한다. 
'''
titanic = sns.load_dataset('titanic')
 
sns.set_style('whitegrid')

#타이타닉 데이터셋의 나이, 좌석등급, 운임을 각각 짝을 지어서 표현한다.
titanic_pair = titanic[['age', 'pclass', 'fare']]

g = sns.pairplot(titanic_pair)

