# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns

titanic = sns.load_dataset('titanic')
sns.set_style('darkgrid')

fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,3,1)
axe2 = fig.add_subplot(1,3,2)
axe3 = fig.add_subplot(1,3,3)

sns.distplot(titanic['fare'], ax=axe1)
sns.kdeplot(x='fare', data=titanic, ax=axe2)
sns.histplot(x='fare', data=titanic, ax=axe3)

axe1.set_title('titanic fare - hist/ked')
axe2.set_title('titanic fare - ked')
axe3.set_title('titanic fare - hist')

plt.show()


