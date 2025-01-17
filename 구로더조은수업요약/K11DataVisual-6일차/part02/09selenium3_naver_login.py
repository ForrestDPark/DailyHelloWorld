# -*- coding: utf-8 -*-
#셀레니움 모듈과 드라이버를 로드한다.
from selenium import webdriver
driver = webdriver.Chrome('./driver/chromedriver.exe')

#암묵적으로 3초간 대기한다.  
driver.implicitly_wait(3)
 
#네이버 로그인 페이지로 이동한다. 
url = 'https://nid.naver.com/nidlogin.login'
driver.get(url)

'''
단일 엘리먼트에 접근하기 위한 메서드 
find_element_by_name()
find_element_by_id()
find_element_by_xpath()
find_element_by_css_selector()
find_element_by_class_name()
find_element_by_tag_name()

만약 복수 엘리먼트에 접근하려면 위 메서드에 s를 붙여준다. 
find_elements_by_css_selector 즉 element에 s를 붙이면된다. 
'''
# send_keys() : input태그에 지정한 값을 입력한다. 
driver.find_element_by_name('id').send_keys('nakjasabal')
driver.find_element_by_name('pw').send_keys('******')

driver.implicitly_wait(5)
# xpath로 지정한 엘리먼트를 클릭한다. 즉 로그인 버튼을 누른다.
driver.find_element_by_xpath('//*[@id="log.login"]').click()

