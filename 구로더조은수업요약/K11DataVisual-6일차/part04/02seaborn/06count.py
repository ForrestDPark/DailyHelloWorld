# -*- coding: utf-8 -*- 
import matplotlib.pyplot as plt
import seaborn as sns

'''
빈도그래프 : 각 범주에 속하는 데이터의 갯수를 막대그래프로 표현한다.
'''
titanic = sns.load_dataset('titanic')
sns.set_style('whitegrid')

fig = plt.figure(figsize=(15, 5))   
axe1 = fig.add_subplot(1, 3, 1)
axe2 = fig.add_subplot(1, 3, 2)
axe3 = fig.add_subplot(1, 3, 3)

#빈도그래프의 기본값. palette옵션을 통해 그래프의 색깔을 표현한다.  
sns.countplot(x='class', palette='Set1', data=titanic, ax=axe1) 
#hue옵션에 who를 추가한다. 즉, 남성/여성/어린이로 막대그래프를 분리한다.
sns.countplot(x='class', hue='who', palette='Set2', data=titanic, 
              ax=axe2) 
#dodge옵션을 추가한다. 즉, 축 방향으로 분리하지 않고 누적그래프를 출력한다.
sns.countplot(x='class', hue='who', palette='Set3', dodge=False, 
              data=titanic, ax=axe3)       

axe1.set_title('titanic class')
axe2.set_title('titanic class - who')
axe3.set_title('titanic class - who(stacked)')

plt.show()

