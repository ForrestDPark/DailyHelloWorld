# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns

titanic = sns.load_dataset('titanic')
sns.set_style('darkgrid')

fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,2,1)
axe2 = fig.add_subplot(1,2,2)

sns.regplot(x='age', y='fare', data=titanic, ax=axe1)
sns.regplot(x='age', y='fare', data=titanic, ax=axe2, fit_reg=False)

plt.show()

