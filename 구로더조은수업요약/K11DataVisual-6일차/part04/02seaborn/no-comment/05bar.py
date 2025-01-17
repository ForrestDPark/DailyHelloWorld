# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns

titanic = sns.load_dataset('titanic')
print(titanic.head()) 
print(titanic.tail(10)) 
print(titanic.info())
print(titanic.describe()) 
print(titanic.describe(include='object'))
print(titanic['who'].value_counts())

sns.set_style('whitegrid')
fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,3,1)
axe2 = fig.add_subplot(1,3,2)
axe3 = fig.add_subplot(1,3,3)

sns.barplot(x='sex', y='survived', data=titanic, ax=axe1)
sns.barplot(x='sex', y='survived', hue='class', data=titanic, ax=axe2)
sns.barplot(x='sex', y='survived', hue='class', dodge=False, data=titanic, ax=axe3)

axe1.set_title('titanic survived - sex')
axe2.set_title('titanic survived - sex/class')
axe3.set_title('titanic survived - sex/class(stacked)')

plt.show()

