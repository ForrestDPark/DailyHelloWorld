# -*- coding: utf-8 -*-
import pandas as pd
import matplotlib.pyplot as plt
'''
버블차트(Bubble)
: 실린더 갯수를 나타내는 정수를 해당 열의 최대값 대신 상대적 크기를
나타내는 비율로 계산해서 점의 크기를 다르게 표시한다. 
이처럼 점의 모양이 비눗방울 같다고 해서 '버블차트'라고 부른다. 
'''
#그래프 스타일 지정
plt.style.use('default')

#csv파일을 데이터프레임으로 변환
df = pd.read_csv('../data/auto-mpg.csv', header=None)

#컬럼명 지정
df.columns = ['mpg','cylinders','displacement','horsepower','weight',
              'acceleration','model year','origin','name']

#실린더 갯수의 상대적 비율을 계산하여 시리즈를 생성
cylinders_size = df.cylinders / df.cylinders.max() * 300
print(cylinders_size)
'''
c : 점의 색깔 지정
s : 점의 크기 지정
alpha : 투명도 지정
marker : 마커의 모양
cmap : 색깔을 정하는 컬러맵
'''
df.plot(kind='scatter', x='weight', y='mpg', c='coral', 
        figsize=(10,5), s=cylinders_size, alpha=0.3, marker='o', cmap='viridis')
plt.title('Scatter Plot : mpg-weight-cylinders')

#출력된 그래프를 png파일로 저장한다.(이 경우 배경은 흰색으로 지정된다.) 
plt.savefig("../save/scatter.png")
#transparent 옵션을 통해 배경색을 투명하게 저장할 수 있다. 
plt.savefig("../save/scatter_transparent.png", transparent=True)
'''
C:\02Workspaces\K03FrontEnd\test 하위에 'PNG이미지테스트.html'를 
참조하여 배경이 투명한 PNG 이미지를 확인한다. 
'''
plt.show()

