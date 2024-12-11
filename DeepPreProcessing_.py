def DEEP_0_GPU_SETTING__macOS():
    """
    # #
    ## DEEP_0_GPU_SETTING__macOS()
    """
    y(" - torch , CUDA system check and model download")
    import torch
    print(yellow(f" 📌 torch version : {torch.__version__}"))
    print(yellow(f" 📌 torch  backend.mps is built : {torch.backends.mps.is_built()}"))
    print(yellow(f" 📌 torch backend.mps is available : {torch.backends.mps.is_available()}"))
    print(yellow(f" 📌 torch cuda is available: {torch.cuda.is_available()}"))

    # device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    y(" - Apple silicon user => Metal Performance Shaders 가속을 사용함. ")
    device = "mps" if torch.backends.mps.is_available() and torch.backends.mps.is_built() else "cpu"
    print(red(f" - Using {device} device",b=True))
    tensor = torch.FloatTensor([1,2,3]).to(device)
    y(" - pytorch mps 가속 불가능 발생경우 지원안되는 경우도 돌아게게끔 환경 설정함. ")
    import os
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] ="1"

def DEEP_0_Image_to_TEXT(image_addr):
    """
    
    ## generated_text = DEEP_0_Image_to_TEXT(image_addr="/handwritten_image/Hello.png")
    
    """
    
    start_time = record_processing_time(start= True)
    import warnings ; warnings.filterwarnings('ignore')
    from transformers import TrOCRProcessor , VisionEncoderDecoderModel
    import torch
    from PIL import Image
    # load image from the IAM database 
    image = Image.open(image_addr).convert("RGB")
    image_show(image_addr)
    
    y("[Info] load pretrained TrOCRProcessor")
    processor = TrOCRProcessor.from_pretrained('microsoft/trocr-base-handwritten')
    
    y("[Info] load  pretrained VisionEncoder Decoder model")
    model = VisionEncoderDecoderModel.from_pretrained('microsoft/trocr-base-handwritten')

    pixel_values = processor(images=image, return_tensor ='pt').pixel_values

    if type(pixel_values)==type([]):
        y("pixel value tesor 변환")
        pixel_values = torch.tensor(pixel_values, dtype=torch.float32)

    print(yellow(f" -pixel_values shape: {pixel_values.shape}") )

    generated_ids = model.generate(pixel_values)
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

    y(f" image to text 변환 결과 : {generated_text}")
    record_processing_time(end=True, started_time= start_time)
    return generated_text




## Plot setting 
def plotSetting(pltStyle="seaborn-v0_8", setting_info =False ):
    '''
    ## plotSetting(pltStyle="default")
    ## plotSetting(pltStyle="seaborn-v0_8")
    ## plotSetting(pltStyle="Solarize_Light2")
    ## plotSetting(pltStyle="fivethirtyeight")
    ## plotSetting(pltStyle="grayscale")

    '''

    if setting_info:
        import warnings ;warnings.filterwarnings('ignore')
        import sys ;sys.path.append("../../../")
        import os 
        print(blue(f"  ⁍ 현재 경로의 폴더 목록 --",True))
        count =1
        for order,file in enumerate(os.listdir(os.getcwd())):
            if os.path.isdir(os.path.join(os.getcwd(),file)):
                print(yellow(f"  폴더{count} :  {str(os.path.join(os.getcwd(),file))}"))
                count +=1
        
        print(blue("../ +  ../../ 경로 python path 에 추가. "))
        sys.path.append("../")
        sys.path.append("../../")
        
        
        print(blue(f"◎ 주피터 가상환경  : {os.environ['CONDA_DEFAULT_ENV']}",True))
        print(blue(f"◎ Python 설치 경로:{sys.executable}",True))
        print(blue(f"◎ Graph 한글화 Setting",True))
        
        def package_list_save_text():
            ## last update : 2024.10.18
            import sys
            import subprocess
            # 파이썬 패키지 목록을 실행 결과로 저장
            output = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'])
            # 결과를 디코딩하여 문자열로 변환
            output_string = output.decode('utf-8')
            # 메모장을 열고 결과를 붙여넣기
            with open("package_list.txt", "w", encoding='utf-8') as f:
                f.write(output_string)
            print("패키지 목록이 package_list.txt 파일에 저장되었습니다.")
        package_list_save_text()
        
    # graph style seaborn
    import matplotlib.pyplot as plt # visiulization
    import platform
    from matplotlib import font_manager, rc # rc : 폰트 변경 모듈font_manager : 폰트 관리 모듈
    plt.style.use(pltStyle)
    plt.rcParams['axes.unicode_minus'] = False# unicode 설정
    plt.rcParams['font.family'] = 'Arial Unicode MS' # or another suitable font
    
    if platform.system() == 'Darwin': rc('font', family='AppleGothic') # os가 macos
    elif platform.system() == 'Windows': # os가 windows
        path = 'c:/Windows/Fonts/malgun.ttf' 
        font_name = font_manager.FontProperties(fname=path).get_name()
        rc('font', family=font_name)
    else:
        print("Unknown System")
    print(colored_text("  - ◎ matplot graph set complete",'blue',bold=True))
    # print(rainbow_green(f"✻✻✻✻______{imo*1} {Title} {imo*1}______✻✻✻✻",True))

##df display 
def df_display_centered(df, message=""):
    from IPython.display import display, HTML
    import pandas as pd 
    if message=="":
        message =f" - SHAPE : {df.shape}"
    if type(df) != type(pd.DataFrame()):
        df=pd.DataFrame(df)
    # print(green(message))
    display(HTML('<div style="text-align: center; margin-left: 30px;">{}</div>'.format(df.to_html().replace('<table>', '<table style="margin: 0 auto;">'))))

## image show
def image_show(img_addr="./hh_image_1.jpg"):
    from PIL import Image
    import matplotlib.pyplot as plt
    plt.figure(figsize= (8,4))
    plt.imshow(Image.open(img_addr))
    plt.axis('off')
    plt.show()

## code processing time record 
def record_processing_time(start=False, end=False, started_time =""):
    """
    ## start_time = record_processing_time(start=True)
    ## record_processing_time(end=True, started_time= start_time)
    """
    import time # time 라이브러리 import
    if start == True:
        start = time.time() # 시작
        return start
    if end :
        end = time.time()
        print(r_cy(f"process time : {time.time()-started_time:.4f} sec")) # 종료와 함께 수행시간 출력
    time.sleep(1) # 측정하고자 하는 코드 부

## TEXT Functions 
def imd(image_address,width =700, height=300):print(f'<br><img src = "{image_address}" width="{width}" height="{height}"/><br>')
def colored_text(text, color='default', bold=False):
    '''
    #### 예시 사용법
    print(colored_text('저장 하지 않습니다.', 'red'))
    print(colored_text('저장 합니다.', 'green'))
    default,red,green,yellow,blue, magenta, cyan, white, rest
    '''
    colors = {
        'default': '\033[99m',
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',  # 보라색
        'cyan': '\033[96m',
        'white': '\033[97m',
        'black': '\033[30m',  # 검은색
        'bright_black': '\033[90m',  # 밝은 검정색 (회색)
        'bright_red': '\033[91m',  # 밝은 빨간색
        'bright_green': '\033[92m',  # 밝은 초록색
        'bright_yellow': '\033[93m',  # 밝은 노란색
        'bright_blue': '\033[94m',  # 밝은 파란색
        'bright_magenta': '\033[95m',  # 밝은 보라색
        'bright_cyan': '\033[96m',  # 밝은 청록색
        'bright_white': '\033[97m',  # 밝은 흰색
        'reset': '\033[0m'
    }

    # 무지개 색 추가 (RGB 값 사용)
    rainbow_colors = [
        '\033[38;2;255;0;0m',  # 빨간색
        '\033[38;2;255;127;0m',  # 주황색
        '\033[38;2;255;255;0m',  # 노란색
        '\033[38;2;0;255;0m',  # 초록색
        '\033[38;2;0;255;127m',  # 청록색
        '\033[38;2;0;0;255m',  # 파란색
        '\033[38;2;127;0;255m',  # 보라색
    ]

    # 무지개 색 추가 (색상 명칭)
    colors.update({
        'rainbow_red': rainbow_colors[0],
        'rainbow_orange': rainbow_colors[1],
        'rainbow_yellow': rainbow_colors[2],
        'rainbow_green': rainbow_colors[3],
        'rainbow_cyan': rainbow_colors[4],
        'rainbow_blue': rainbow_colors[5],
        'rainbow_magenta': rainbow_colors[6],
    })

    color_code = colors.get(color, colors['default'])
    bold_code = '\033[1m' if bold else ''
    reset_code = colors['reset']

    return f"{bold_code}{color_code}{text}{reset_code}"
def blue(str, b=False):return colored_text(str, 'blue', bold=b)
def yellow(str, b=False):return colored_text(str, 'yellow', bold=b)
def y(string):
    if type(string) != type("ss"):
        string= str(string)
        print(r_y(''+string))
    else: print(r_y('🥇'+string))
def y_(string):
    if type(string) != type("ss"):
        string= str(string)
        print(r_y('🥇'+string))
    else: print(r_y('🥇'+string))
def g(string):
    if type(string) != type("ss"):
        string= str(string)
        print(green(string))
    else: print(green(string))
def red(str, b=False):return colored_text(str, 'red', bold=b)
def green(str, b=False):return colored_text(str, 'green', bold=b)
def magenta(str, b=False):return colored_text(str, 'magenta', bold=b)
def r_red(str, b=False):return colored_text(str, 'rainbow_red', bold=b)
def r_orange(str, b=False):return colored_text(str, 'rainbow_orange', bold=b)
def r_y(str, b=False):return colored_text(str, 'rainbow_yellow', bold=b)
def r_g(str, b=False):return colored_text(str, 'rainbow_green', bold=b)
def r_cy(str, b=False):return colored_text(str, 'rainbow_cyan', bold=b)
def r_b(str, b=False):return colored_text(str, 'rainbow_blue', bold=b)
def r_m(str, b=False):return colored_text(str, 'rainbow_magenta', bold=b)
def rainbow_text(text,bold =False):
    """텍스트를 무지개색으로 한 글자씩 출력합니다."""
    rainbow_colors = [
        '\033[38;2;255;0;0m',  # 빨간색
        '\033[38;2;255;127;0m',  # 주황색
        '\033[38;2;255;255;0m',  # 노란색
        '\033[38;2;0;255;0m',  # 초록색
        '\033[38;2;0;255;127m',  # 청록색
        '\033[38;2;0;0;255m',  # 파란색
        '\033[38;2;127;0;255m',  # 보라색
    ]
    colored_text = ''
    for i, char in enumerate(text):
        colored_text += rainbow_colors[i % len(rainbow_colors)] + char
    colored_text += '\033[0m'  # 색상 초기화
    bold_code = '\033[1m' if bold else ''
    return f"{bold_code}{colored_text}"

def yd(explain, df ,heading=3):
    import pandas as pd 
    if type(df) !=type(pd.DataFrame()):
        df = pd.DataFrame(df)
    if heading ==0:
        y(f" - {explain} [ SHAPE :{df.shape}]") 
        df_display_centered(df)
    else:
        y(f" - {explain} [HEAD :{heading}/ SHAPE :{df.shape}]")
        df_display_centered(df.head(heading))
def gd(order,exp , df ,heading=3):
    import pandas as pd 
    if type(df) !=type(pd.DataFrame()):
        df = pd.DataFrame(df)
    from IPython.display import display
    g(f"{order} {exp} "); 
    if heading ==0:
        y(f"   - Displayed rows= {len(df)}/{len(df)}")
        # if int(df.isna().sum()) !=0:
        #     g(f"   Null included rows: {df.isnull().sum()}")
        df_display_centered(df)
    else:
        y(f"   - Displayed rows= {heading}/{len(df)}")
        # if int(df.isna().sum()) !=0:
        #     g(f"   Null included rows: {df.isnull().sum()}")
        df_display_centered(df.head(heading))
if __name__ == "__main__":
    
    with open("update_log.txt") as update_log:
        log = update_log.read()
        print(yellow(f"{log}"))
    
        import pandas as pd ,sys
        # input_data = pd.read_csv('/Users/forrestdpark/Desktop/PDG/Python_/BerryMLcompetetion/BerryMachineLearning/예선연습_2023_tomato/Data/2023_smartFarm_AI_hackathon_dataset.csv')
        while True : 
            print(green("프로그램 시작"))
            #  plotSetting()
            #  dataInfo(input_data)
            print(green("다시 실행하시겠습니니까?(yes =1, no=0): "))
            restart_query = int(sys.stdin.readline())
            if restart_query == 0:
                break     

''' 
📌 Description :  
    - DataPreprocessing class :
    - ModelTest class : 

📌 Date : 2024.06.02 
📌 Author : Forrest D Park 
📌 Update : 
    ○ 2024.08.07 by pdg : DataInfo 함수 생성
    ○ 2024.08.23  by pdg : DataInfo -> 시계열 데이터 일때 그래프 시각화 하는 기능 추가 
        - 분석때 배운거 다 플랏할수있도록 함수화 하자. 
    ○ 2024.09.02 Mon AM 10:05 py pdg
        - Function module 은 굉장히 업데이트가 많이 일어나기 때문에 업데이트 로그를 따로 파일로 관리하는게 낫다. 
        - 이렇게 주석으로 하는 것보다 내가 적은 시간에 알맞게 시간대랑 날짜랑 업데이트 내용이 표현되어서 txt 파일에 저장되고
            그렇게 저장된 텍스트 파일은 로그로 남고 Cummon 의 main 을 실행하면 업데이트 로그파일이 프린트되도록 하자. 
        - 최근에 함수만들면 아무 설명도 없이 그냥 띡 가져다 붙였는데 설명을 좀 써놓자. 
        - data_column_info 가아니라 명칭을 바꾸어두자. 
    
    2024.09.06
        - data watch range -> +1 추가
'''

"""
    sns palettes
        # deep: 푸른색 계열의 짙은 색상 팔레트 --
        # muted: 푸른색, 녹색, 주황색, 빨간색 계열의 부드러운 색상 팔레트
        # pastel: 밝고 부드러운 파스텔 색상 팔레트
        # bright: 밝고 선명한 색상 팔레트
        # dark: 어둡고 짙은 색상 팔레트
        # colorblind: 색맹 친화적인 팔레트 -----
        # husl: 색상 대비가 좋은 팔레트 --
        # cubehelix: 회전하는 색상 팔레트
        # Accent: 강렬한 색상 팔레트
        # Paired: 12가지 색상의 쌍으로 구성된 팔레트 --
        # Set1: 8가지 색상의 팔레트
        # Set2: 8가지 색상의 팔레트 ----
        # Set3: 12가지 색상의 팔레트 ---
        # viridis: 녹색에서 노란색으로 이어지는 밝고 선명한 팔레트 (색맹 친화적) --
        # plasma: 보라색에서 노란색으로 이어지는 밝고 선명한 팔레트 (색맹 친화적)
        # magma: 보라색에서 노란색으로 이어지는 밝고 뜨거운 팔레트 (색맹 친화적)
        # inferno: 검은색에서 노란색으로 이어지는 뜨거운 팔레트 (색맹 친화적)
        # cividis: 푸른색에서 노란색으로 이어지는 밝고 선명한 팔레트 (색맹 친화적)
        # coolwarm: 푸른색에서 빨간색으로 이어지는 균형 잡힌 팔레트 ---
        # bwr: 파란색에서 흰색, 빨간색으로 이어지는 팔레트 --
        # RdBu: 빨간색에서 흰색, 파란색으로 이어지는 팔레트 ---
        # RdGy: 빨간색에서 흰색, 회색으로 이어지는 팔레트
        # PRGn: 빨간색에서 푸른색, 녹색으로 이어지는 팔레트
        # PiYG: 핑크색에서 빨간색, 녹색, 노란색으로 이어지는 팔레트
        # BrBG: 갈색에서 푸른색, 녹색으로 이어지는 팔레트
        # PuOr: 보라색에서 주황색으로 이어지는 팔레트
        # RdYlGn: 빨간색에서 노란색, 녹색으로 이어지는 팔레트
        # Spectral: 보라색에서 빨간색, 노란색, 녹색으로 이어지는 팔레트 -----
"""