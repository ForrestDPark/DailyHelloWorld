# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import seaborn as sns

titanic = sns.load_dataset('titanic')
sns.set_style('whitegrid')

fig = plt.figure(figsize=(15, 5))
axe1 = fig.add_subplot(1,2,1)
axe2 = fig.add_subplot(1,2,2)

sns.stripplot(x="class", y="age", data=titanic, ax=axe1)
sns.swarmplot(x="class", y="age", data=titanic, ax=axe2)

axe1.set_title('Strip Plot')
axe2.set_title('Swarm Plot')

plt.show()

