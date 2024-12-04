# 12.3 qcut function update
# 12.2 smote, nearmiss update
 ## 2024.12.1 scaling update, 
## outlier feature dist update, skewness update
## 2024.11.30 processing time function 
## 2024.11.29 yd, dfdisplay update, outlier udpate
## 2024.11.28 Continuous Target col processing upgrade
## 2024.11.28 OHE encoding upgrade
## 2024.11.28 Feature engineering part upgrade
## 2024.11.27 upgrade...
## 2024.11.26 oversampling, 및 함수 재처리 
## 2024.11.25 update DPP 함수 분리 .
class Basic:
    def __init__(self):
        import matplotlib.pyplot as plt, numpy as np, pandas as pd
        from IPython.display import display as disp, HTML 
        self.pd = pd
        self.np = np
        self.plt =plt
        self.display = disp
        self.version = "1.0.1"
        self.last_update ="2024.10.28"
    def __str__(self):
        return red(f"Custom Func Version : {self.version} -update {self.last_update}",b=True)
    def __str__(self):
        return yellow(f"""
    ** 전처리 과정 순서를 따라서 데이터를 확인하세요  **

    #1. Step1. 데이터 Target 균일도, 독립, 종속, 결측치  확인: 
        > target = step_1_Raw_Taregt_EDA(train,test,submission)
        > 

    2. 종속변수와 독립변수를 분할하여 train_x, train_y 를 생성 : 
        >>train_x,train_y,test_x=  step_2_Indep_dep_val_split(train,test,target_colname= 'target', drop_test ='id')

    3. 수치형 칼럼과 범주형 칼럼을 분류하기 위해서 칼럼분포를 시각화(hist, boxplot) 하고 수치형데이터 의 분포와 왜도확인: 
        >>  step_3_0_dataInfo2(df), 
        >>  step_3_1_numeric_column_dist_boxplot(train_x)
        >>  step_3_2_Skewness_check(train) 

    4. Target 값의 분포를 확인하여 데이터의 균일도를 확인합니다.(이진분류 타겟일 경우 적용)
        >>  step_4_MLOutput_target_ratio(train_df, target_col="Outcome",graph_show=False)

    5. Outlier 를 확인(0),사용자기준으로 걸르고 최빈값으로 대체(1), zscore, IQR 값으로 확인후 제거(2) : 
        >>  step_5_0_Outlier_check(X_train, col='income_total') =>
        >> train_x= step_5_1_Outlier_processing(train_x,'trestbps',over_val=170,under_val=0, replace_outlier = 'mode')
        >> X_train =  step_5_2_Outlier_erase(X_train, col='income_total', threshold = 3, IQR=True)

    6. 정규화 를 진행합니다. 
        >> train_x_scaled_df,test_x_scaled_df =  step_6_Standardization(train_x,test_x,need_to_scale = ['age','trestbps','chol','thalach'])

    7. 범주형 데이터에 원핫 인코딩을 진행합니다 : 
        >> train_x_encoded_df,test_x_encoded_df =  step_7_OHE_process(train_x,test_x,need_to_encoding = ['sex','cp','restecg','slope','thal'])

    8. 로그 변환 이 필요한 데이터에 로그 변환을 진행합니다. : 
        >> train_x,test_x=  step_8_Log_transform(train_x,test_x, need_to_log_trainsform=['oldpeak'])

    9. 정규화 된 데이터와 범주형 데이터를 병합하여 기존 train_x, test_x 에 붙입니다. 




    기타 : 
    - key_selector
    - quantile_dist_for_binary_output
    - feeature_outlier_graph
    - pairPlot_numeric_cols
    """)

####################################################################################################################################################################################

# print(r_cy("\n======================= step_1_Raw_Taregt_EDA ======================="))
# start_time = record_processing_time(start=True)
# record_processing_time(end=True, started_time= start_time)

################################################################################################################################################


## Raw data processing
def step_0_raw_to_test_submiss(raw_data,target = 'target'):
    """
    # # submission, test 가 없을때 데이터 셋 만들기 
    ## raw_data=pd.read_csv("./캘리포니아집값/train.csv")
    ## train,test,submission, answer =step_0_raw_to_test_submiss(raw_data)
    """
    print(r_cy("=========================== step_0_raw_to_test_submiss =========================== "))
    start_time = record_processing_time(start=True)
    import numpy as np, pandas as pd
    train = raw_data
    test_indices = np.random.choice(train.index, size=50, replace=False)
    test = train.loc[test_indices]
    answer = test[target]
    submission = pd.Series(np.zeros_like(test[target].to_numpy()), name=target)
    test = test.drop(target, axis=1)
    train = train.drop(test_indices, axis =0)
    train['ID'] = train.index
    y_(" Raw data 에서 train,test,submission, answer 를 생성합니다. ")
    print(r_cy(f" \n train size :{train.size} \n test size :{test.size} \n submission:{submission.size}"))
    record_processing_time(end=True, started_time= start_time)
    return train,test,submission, answer

## 1 : TARGET EDA 

def step_1_Raw_Taregt_EDA(train,test, submission, outlier_val =0, info_ =True,id_column='ID'):
    """
    # #TARGET EDA 
    ## target,target_type,obj_col = step_1_Raw_Taregt_EDA(train,test, submission, outlier_val =0)
    
    # #FEATURE 칼럼 EDA 
    ## setp_1_Feature_EDA(train, target, target_type, exclude_col=['id'], cols_target_plt=True)
    
    """
    start_time = record_processing_time(start=True)

    print(r_cy("\n======================= step_1_Raw_Taregt_EDA ======================="))
    import pandas as pd
    
    g("1. RAW DATA CHECK")
    gd("1.1","TRAIN DATA", train)
    gd(1.2, 'TEST DATA', test)
    gd(1.3 ,'SUBMISSION ',submission)
    y_("1.4 TRAIN DATA missing value CHECK. + INFO() ------")
    if info_:
        df_display_centered(pd.DataFrame(train.isna().sum(0)))
        df_display_centered(pd.DataFrame(train.info()))
        missing_cols = train.columns[train.isna().sum() > 0].tolist()
        y_(f" - Missing Value Counted Column : {missing_cols}")
    else:
        print(yellow(" 결측치 및 info 를 생략합니다."))
        
        
    if  train.select_dtypes(include=['object']).any().tolist()!=[]:
        y_(" - OBJECT TYPE DESCRIBE(TRAIN)")
        df_display_centered((train.describe(include='object')))
        objcol = train.describe(include='object').columns.tolist()
        objcol = [i for i in objcol if i !=id_column]
        y_(f'Object type columns w.o id:{objcol}')
    else : objcol=[]
    print(r_g(" ..★★ TARGET VALUE OF THE PROJECT ★★.. : {}".format(submission.columns.tolist()[-1]),b=True))
    target = submission.columns.tolist()[-1]
    plotSetting('default')
    import matplotlib.pyplot as plt
    
    ## Discrete Catigorical TARGET CASE
    if len(train[target].value_counts().index)<20:
        target_type ='Categorical'
        gd("","target value counts",pd.DataFrame(train[target].value_counts().sort_index()),heading=0)
        y_(" -  Target distribution visualization ")
        x= train[target].value_counts().sort_index().index
        y = train[target].value_counts().sort_index().values
        plt.figure(figsize=(6,3), dpi = 150)
        plt.title(f"Target({target}) Distribution")
        plt.xlabel(target)
        plt.ylabel("Counts [#]")
        plt.bar(x,y)
        plt.show()
        
    ## Continuous TARGET CASE   
    else:  
        target_type ='Continuous'
        import seaborn as sns
        import warnings;warnings.filterwarnings('ignore')
        y_(f" - {target} column is continuous range [{min(train[target])} ~ {max(train[target])}]")
        y_(f" - Mean of Target({target}) : {train[target].mean()}")
        plt.figure(figsize=(8,3), dpi = 150)
        plt.title(f"Target({target}) Distribution")
        plt.xlabel(target)
        plt.ylabel("Counts [#]")
        sns.histplot(train[target],kde=True,palette='viridis')
        plt.show()
        
        # figure axes, gen
        y_(" - Continuous target Vis.")
        import matplotlib.pyplot as plt
        plotSetting()
        fig, ax = plt.subplots(figsize=(8,3),dpi=150)
        ax.set_title(f"{target}")
        ax.set_xlabel("days")
        ax.set_ylabel(f"{target} Counts[#]")
        ax.plot(train[target].index,train[target].values)
        
        ## Outlier Visualization 
        if outlier_val ==0:
            outlier_val = min(train[target])*8
        ax.hlines(y=outlier_val,xmin= 0,xmax=len(train[target].index), colors ='red', linestyles='dotted')
        plt.show()
        record_processing_time(end=True, started_time= start_time)
    return submission.columns.tolist()[-1] , target_type, objcol,missing_cols

## Data FE category check
def step_1_0_EDA_DataCategory(train,target,id_column = 'ID'):
    """
    data_type, data_category, missing_cols =step_1_0_EDA_DataCategory(train)
    """
    print(r_cy("\n======================= step_1_0_EDA_DataCategory ======================="))
    start_time = record_processing_time(start=True)
    import warnings ; warnings.filterwarnings('ignore')
    
    import pandas as pd, numpy as np
    df_col = ["data_type", 'target_type', 'target_valance', 'missing_value','zero_missing','obj_col', 'outlier']
    data = {col: [] for col in df_col}
    for cat,target_type in enumerate(['Continuous', 'Categorical']):
        for target_balance in [0, 1]:
            for missing_value in [0, 1]:
                for zero_missing in [0,1]:
                    for obj_col in [0, 1]:
                        for outlier in [0,1]:
                            data["data_type"].append(f"{cat+1}-{len(data['data_type']) + 1}")
                            data["target_type"].append(target_type)
                            data["target_valance"].append(target_balance)
                            data["missing_value"].append(missing_value)
                            data['zero_missing'].append(zero_missing)
                            data["obj_col"].append(obj_col)
                            data["outlier"].append(outlier) #  아니면 1 또는 다른 논리에 따라 값을 설정
                            

    data_category = pd.DataFrame(data, columns=df_col)
    # df_display_centered(data_category['explain'])
        
    # unique 가 20이하면 일단 discret 으로 판단. target type 판단
    target_type =  'Categorical' if len(train[target].value_counts().index)<20 else 'Continuous'
    y_(f" - [target type] : {str(target_type)}")
    ## target valence check
    class_counts = train[target].value_counts(normalize=True)
    max_ratio = class_counts.max()
    min_ratio = class_counts.min()
    if max_ratio / min_ratio >1.5:
        y_(f" - [target valence] : 1 ( ∵ 최대 target/최소 target > 1.5({max_ratio:.1f}:{min_ratio:.1f}))")
        target_valance =0
        
    else:
        y_(f" - [Valenced Output] 최대 target/최소 target < 1.5.({max_ratio:.1f}:{min_ratio:.1f})")
        print( 'balanced')
        target_valance= 1
        
    # 결측치 검사. 
    missing_cols = train.columns[train.isna().sum() > 0].tolist()
    missing_value = 0 if missing_cols==[] else 1
    y_(f" - [missing value] :{missing_value} (∵ missing col :{missing_cols})")

    ## 0 이 결측치인 경우 어떻게 함?
    train_copy = train.copy()
    for col in train.select_dtypes(include='number').columns.tolist():
        train_copy[col] = train_copy[col].replace(0, np.nan)
    zero_missing_cols = train_copy.columns[train_copy.isna().sum() > 0].tolist()
    zero_missing_cols = [i for i in zero_missing_cols if i !=target]
    zero_missing = 0 if zero_missing_cols==[] else 1
    yd(f"[zero missing] :{zero_missing} (∵)",train_copy[zero_missing_cols].isna().sum(),heading=0)

    # object type column 존재 여부 
    if  train.select_dtypes(include=['object']).any().tolist()!=[]:
        objcol = train.describe(include='object').columns.tolist()
        objcol = [i for i in objcol if i !=id_column]
        
    else : objcol=[]
    obj_col = 0 if objcol ==[] else 1
    y_(f'[obj_col]: {obj_col} ∵{objcol}')
    
    # outlier 존재 여부.. => 왜도 수치 파악해서 간단하게 ..!/ 

    if id_column in train.columns.tolist():
        train_copy=train.copy().drop(id_column,axis=1)
    else  :train_copy=train.copy()
    stardardized_cols= step_3_2_Skewness_check(train_copy)
    stardardized_cols = [i for i in stardardized_cols if i !=target]
    feature_columns = train_copy.drop(target, axis=1).columns.tolist() 
    feature_types = [(i,'Dis') if len(train_copy[i].value_counts().index) < 20 else (i,'Con') for i in feature_columns]
    y_(f" 이산형 features")
    dis_type_col =[]
    for i in feature_types:
        if i[1]=='Dis':
            print(yellow(f"  {i}"))
            dis_type_col.append(i[0])
            

    train_outliers=train_copy.drop(stardardized_cols, axis=1)
    train_outliers=train_copy.drop(target, axis=1)
    outlier_col = [i for i in train_outliers.columns.tolist() if i not in dis_type_col]
    outlier = 0 if train_outliers[outlier_col].columns.tolist==[] else 1
    y_(f" [outlier] : {outlier} {str(train_outliers.columns.tolist())}")


    

    data_info = [target_type, target_valance,missing_value,zero_missing,obj_col,outlier]

    target_type, target_valance, missing_value, zero_missing, obj_col, outlier = data_info
    filtered_df = data_category[
        (data_category["target_type"] == target_type) &
        (data_category["target_valance"] == target_valance) &
        (data_category["missing_value"] == missing_value) &
        (data_category["zero_missing"] == zero_missing) &
        (data_category["obj_col"] == obj_col) &
        (data_category["outlier"] == outlier)
    ]
    y_(f" 이 데이터의 데이터 타입은 {filtered_df['data_type'].values[0]} 입니다")
    
    filtered_df['missing_cols'] =f"{str(missing_cols)}"
    filtered_df['zero_missing_cols'] =f"{str(zero_missing_cols)}"
    filtered_df['outlier_cols'] =f"{str(outlier_col)}"
    filtered_df['obj_cols'] =f"{str(objcol)}"
    
    
    
    record_processing_time(end=True, started_time= start_time)
    return filtered_df

## 1 : FEATURE EDA 
def setp_1_Feature_EDA(train, target, target_type ,exclude_col=[], cols_target_plt=True, pair_plot =True):
    """ 
    # #FEATURE 칼럼 EDA 
    ## setp_1_Feature_EDA(train, target, target_type ,exclude_col=['id'], cols_target_plt=True, pair_plot =True)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= setp_1_Feature_EDA ======================="))
    
   
    
    import matplotlib.pyplot as plt, seaborn as sns, pandas as pd, numpy as np
    import warnings ; warnings.filterwarnings('ignore')
    # target = train_y.name
    numeric_cols = train.select_dtypes(include='number').columns.tolist()
    numeric_cols =set(numeric_cols)-set([target]+exclude_col)
    
    if cols_target_plt and target_type =='Categorical':
        y_(" - column  vs target 분포 ")
        print(green(f" -  {numeric_cols} 분포"))
        total_graph_num=len(numeric_cols)
        total_row = total_graph_num //2 + total_graph_num%2
        plt.figure(figsize= (8,total_row*2.5))

        for order,feature in enumerate(numeric_cols):
            x  = train.groupby(target).mean().reset_index()[target]
            y = train.groupby(target).mean().reset_index()[feature]
            plt.subplot(total_row,2,order+1)
            plt.title(f"{feature} vs {target}")
            plt.bar(x,y)
            plt.xlabel(target)
            plt.ylabel(feature+" Count")
            plt.tight_layout()
        plt.show()
    if cols_target_plt and target_type =='Continuous' :
        y_(" - Features box plot dist")
        rows_of_plot = len(numeric_cols)//7 if len(numeric_cols)%7==0 else len(numeric_cols)//7+1
        plt.figure(figsize=(30,15))
        plt.style.use("ggplot")
        plt.suptitle("Features box plot dist",fontsize= 30)
        for order,feature in enumerate(numeric_cols):
            plt.subplot(rows_of_plot,7,order+1)
            plt.title(feature, fontsize = 28)
            plt.boxplot(train[feature])
        plt.show()
        if pair_plot:
            if train.shape[0] >2000:
                y_("train size 가 1000이상 random sample 1000개를 뽑아 pair plot 합니다")
                sample_indices = np.random.choice(train.index, size=1000, replace=False)
                train = train.loc[sample_indices]
            # plotSetting()
            plt.style.use("fivethirtyeight")
            y_(" - Pair plott of numerical features ")
            g = sns.pairplot(pd.concat([train[numeric_cols],train[target]],axis=1), kind='reg', diag_kind='kde',  # diag_kind='kde'는 대각선에 kernel density estimation을 표시
                    height=2, aspect=1.2,  # 그래프 크기 조절
                    plot_kws={'line_kws':{'color':'red', 'lw':2}},  # 회귀선 색깔과 두께 설정
                    diag_kws={'color':'skyblue', 'shade':True})  # 대각선 kde 색깔과 음영 설정

            g.fig.suptitle('Pair Plot with Regression Lines', y=1.02) # 전체 제목 추가
            plt.show()
    
    y_(" - CORRELATION CHECK (HEAT MAP) about continuous")
    plt.figure(figsize = (12,10))
    ax = sns.heatmap(data = train.corr(method ='pearson'), annot= True, fmt='.2f', linewidths = .5, cmap='Blues')
    plt.show()
        
    corr_table = train[list(numeric_cols)+ [target]].corr()
        
        
    
    # display(corr_table.describe())
    corr_rank =[]
    corr_rank_name = []
    max_corr_rank = max(abs(corr_table.describe()))
    standard_of_comparing_corr= 0.3
    for col in corr_table.columns:
        for row in corr_table[col].index:
            ## 같은 피쳐끼리 비교 제외 0.5이하 corr 제외 
            if (standard_of_comparing_corr <= abs(corr_table[col][row])) & (row!=col):
                ## row col 반대로 해도 똑같으므로 제외   
                if f"{row} - {col}" not in corr_rank_name:
                    # print(yellow(f"{col} vs {row} : {abs(corr_table[col][row]):.1f}")) 
                    corr_rank.append(abs(corr_table[col][row]))
                    corr_rank_name.append(f"{col} - {row}")
    corr_rank_table=pd.DataFrame(corr_rank, index=corr_rank_name, columns=['corr']).sort_values(by='corr')
    
    y_(f" ⭐️ RESULT(>{standard_of_comparing_corr}) Features")
    df_display_centered(corr_rank_table)
    if corr_rank:
        y_(f" - 가장 큰 공산성 : {corr_rank_name[np.argmax(corr_rank)]} : {np.max(corr_rank):.2f}")
    else:
        y_(" - 공산성이 있는 칼럼이 없습니다. ")
    ## target poly list top
    step_2_EDA_if_poly_top_corr_list(train,target)
    
    plt.show()
    record_processing_time(end=True, started_time= start_time)

## 1 : target vs Feature comparison (Outlier vs Standard )
def step_1_Outlier_under_over_compare(train,target,outlier_val=8000):
    """
    # # Comparison for Outlier value 
    ## step_1_Outlier_under_over_compare(train,target,outlier_val=8000)
    """
    print(r_cy("\n======================= step_1_Outlier_under_over_compare ======================="))
    import pandas as pd
    import matplotlib.pyplot as plt, seaborn as sns
    # outlier check
    train_outlier=train[train[target]<=outlier_val]
    df_display_centered(train_outlier.head(3))
    y_("-  train_outlier (rental < 8000)'s feature  mean values ")
    print(train_outlier.mean())
    

    y_(" - Under vs Over outlier feature's mean values ")
    under_outlier_mean = train_outlier.mean()
    over_outlier_mean = train[train[target]>=8000].mean()
    # grayscale
    plotSetting('grayscale')
    def compare(idx):
        x = [f"{outlier_val} <="+under_outlier_mean.index[idx],f"{outlier_val} >"+under_outlier_mean.index[idx] ]
        y = [under_outlier_mean.values[idx],over_outlier_mean.values[idx] ]
        data = pd.DataFrame({'feature': x, 'value': y})
        plt.figure(figsize= (10,1))
        plt.title( under_outlier_mean.index[idx])
        width = 0.4 # 막대 너비 조절 (값을 줄이면 막대가 가늘어짐)
        plt.barh(data['feature'], data['value'], height=width, color=sns.color_palette("Set2", 2),align='edge') #color는 seaborn 팔레트 사용
        plt.xlabel("Mean value ")
        plt.show()
    for i in range(len(train_outlier.mean())):
        compare(i)

## 1 : Special Feature vs Target EDA 일반화 필요 ..
def step_1_Special_col_EDA(train,feature, target):
    """
    일반화 필요 ..
    # #Special Feature vs Target EDA
    ## step_1_Special_col_EDA(train,"type", target)
    """
    print(r_cy("\n======================= step_1_Special_col_EDA ======================="))
    import pandas as pd
    feature_splited_dict = {}
    for i in train[feature].value_counts().index:
        feature_splited_dict[i]=train[train[feature]==i]
    # display(feature_value_counts)
    
    import matplotlib.pyplot as plt, seaborn as sns
    plt.style.use("ggplot")
    y(f" - feature 에 따른 target 개수  ")
    sns.countplot(data = train, x = feature, hue=target)
    plt.title(f" {feature} 에 따른 {target} 개수")
    plt.show()
    plt.figure(figsize= (6,3))
    plt.suptitle(f"white/red 별 {target} 값 비교", fontsize = 20)
    
    y(" - white")
    plt.subplot(1,2,1)
    sns.barplot(x=feature_splited_dict['white'][target].value_counts().index, y=feature_splited_dict['white'][target].value_counts())
    plt.xlabel('white')
    y(" - red")
    plt.subplot(1,2,2)
    sns.barplot(x=feature_splited_dict['red'][target].value_counts().index, y=feature_splited_dict['red'][target].value_counts())
    plt.xlabel('red')

## 2 : [FE] OBJECT type -> 수치 가 아니면 킬람 식제
def step_2_0_FE_erase(train,test, object_cols = [], delete = False, to_numuric =False):
    '''
    # # Erase some feature from train and test dataset
    ## train, test = step_2_0_FE_erase(train,test, object_cols = [])
    '''
    print(r_cy("\n======================= step_2_0_FE_erase ======================="))
    y(f" - Object type 변수 {str(object_cols)}를 삭제합니다. ")
    return train.drop(object_cols, axis = 1) , test.drop(object_cols, axis =1)

## 2. : [FE] OBJECT type -> 다이렉트 인코딩으로 범주형 칼럼 수치화
def step_2_0_FE_Direct_Encoding(train, cate_col, mapping_dict ={}):
    """ 
    # #[FE CASE.2]다이렉트 인코딩으로 범주형 칼럼 수치화
    ## type_map = {"white": 1,"red":0}
    ## train = step_2_0_FE_Direct_Encoding(train, 'type',mapping_dict=type_map)
    ## test = step_2_0_FE_Direct_Encoding(test, 'type',mapping_dict=type_map)
    """
    print(r_cy("\n======================= step_2_0_FE_Direct_Encoding ======================="))
    import pandas as pd
    train_rep= train.copy()
    if mapping_dict != {}:
        train_rep[cate_col]= train_rep[cate_col].replace(mapping_dict)
        yd("","수치화 된 범주형 칼럼 ",pd.concat([train[cate_col],train_rep[cate_col]],axis=1))
    else:
        print(" mapping 할 dict 를 입력하세요")
    return train_rep

## 2. : [FE] OBJECT type (명목형 범주) Label 인코딩으로 범주형 칼럼 수치화
def step_2_0_FE_Label_encoding(train_x,test_x,obj_cols):
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    for col in obj_cols:
        train_x[col] = le.fit_transform(train_x[col])
        test_x[col]= le.transform(test_x[col])
    
    train_x= train_x.drop(obj_cols,axis=1)
    test_x= test_x.drop(obj_cols,axis=1)

## 2. : [FE] OBject type (순서형 범주)
def step_2_0_FE_OrdinalEncoding(train_x,test_x,objcol, ordered_cat):
    from sklearn.preprocessing import OrdinalEncoder
    oe = OrdinalEncoder(categories=ordered_cat)
    train_x[objcol] = oe.fit_transform(train_x[objcol]).astype(int)
    test_x[objcol] = oe.transform(test_x[objcol]).astype(int)

## 2 : [FE]범주형데이터의 onehot encoding
def step_2_0_FE_OneHotEncoding(train_x,test_x,need_to_encoding = ['sex','cp','restecg','slope','thal']):
    """
    # #범주형 데이터에 원핫 인코딩 진행
    ## train_x,test_x =  step_2_0_FE_OneHotEncoding(train_x,test_x,need_to_encoding = ['sex','cp','restecg','slope','thal'])
    """
    y(f" - {need_to_encoding} 칼럼의 One Hot Encoding 을 진행합니다 ")
    import pandas as pd
    from sklearn.preprocessing import OneHotEncoder 
    ohe = OneHotEncoder(handle_unknown='ignore')
    train_x_encoded = ohe.fit_transform(train_x[need_to_encoding]).toarray()
    test_x_encoded = ohe.transform(test_x[need_to_encoding]).toarray()
    encoded_col = ohe.get_feature_names_out(need_to_encoding)
    y(encoded_col)
    train_x_encoded_df = pd.DataFrame(train_x_encoded, columns=encoded_col)
    test_x_encoded_df = pd.DataFrame(test_x_encoded,columns=encoded_col)
    train_x = pd.concat([train_x,train_x_encoded_df], axis =1).drop(need_to_encoding,axis= 1)
    test_x = pd.concat([test_x,test_x_encoded_df], axis =1).drop(need_to_encoding,axis=1)
    yd("Onhot encoded train x : ",train_x)
    
    return train_x,test_x

## 2 : [FE] CategoryEncoder 
def step_2_0_FE_CategoryEncoding(train_x,test_x,to_en_cols=[]):
    import category_encoders as ce
    category_encoder= ce.BinaryEncoder(cols = to_en_cols)
    train_encoded =category_encoder.fit_transform(train_x[to_en_cols])
    test_encoded =category_encoder.transform(test_x[to_en_cols])
    encoded_column = train_encoded.columns
    train_encoded_df = pd.DataFrame(train_encoded, columns =encoded_column )
    test_encoded_df = pd.DataFrame(test_encoded, columns =encoded_column )
    train_x = pd.concat([train_encoded,train_encoded_df],axis = 1).drop(to_en_cols, axis =1)
    test_x = pd.concat([test_encoded,test_encoded_df],axis = 1).drop(to_en_cols, axis =1)
    
    return train_x, test_x
    
    


## 2-0 : [FE] DATETIME -> 날짜변수가 있을 경우 분리하여 정제
def step_2_0_FE_Seperate_datetime(train_x,date_to_num =False, orderd_week_day =False):
    """
    # #[FE CASE.3] 날짜변수가 있을 경우 분리하여 정제
    ## train=step_2_0_FE_Seperate_datetime(train,date_to_num =True, orderd_week_day =True)
    ## test=step_2_0_FE_Seperate_datetime(test,date_to_num =True, orderd_week_day =True)
    """
    print(r_cy("\n======================= step_2_0_FE_Seperate_datetime ======================="))
    import pandas as pd
    ## Date type validation
    def validate_date(date_text):
        import datetime as dt
        try:
            dt.datetime.strptime(date_text,"%Y-%m-%d")
            return True
        except ValueError:
            print("Incorrect data format({0}), should be YYYY-MM-DD".format(date_text))
            return False
    ##
    y(" - Checking the object columns ar Date type... ")
    object_type_col =train_x.select_dtypes("object").columns.tolist()
    for obj_col in object_type_col:
        if validate_date(train_x[obj_col].iloc[0]):
            y(f" - 📌'{obj_col}'📌 칼럼이 날짜형 데이터 임을 확인!.")
            date_colname = obj_col
            break
    print(yellow(f" - 날짜형 '{date_colname}'칼럼 데이터 샘플: {train_x[date_colname].iloc[0]}"))
    
    ## Date column processing 
    if date_colname and date_to_num:
        from dateutil.parser import parse
        # print(parse("2024-10-23"))
        date_train =train_x.copy()
        ## Object to => DateFormatted
        date_formated=pd.Series(pd.to_datetime(date_train[date_colname]), name = "date_formated")
        ## Week_day name extract
        week_day =pd.Series(date_formated.dt.day_name(), name='week_day')
        
        if orderd_week_day:
            week_day = pd.Series(date_formated.dt.dayofweek, name= 'week_day')
            y_(" - Day names were mapped by orderd number ( Mon :0, Sun:6)")
            result_train=pd.concat([date_formated,
                                pd.Series(date_formated.dt.year, name= 'year'),
                                pd.Series(date_formated.dt.month, name= 'month'),
                                pd.Series(date_formated.dt.day, name= 'day'),
                                pd.Series(week_day,name = 'week_day'),
                                date_train],axis=1)
        
        else: ## Random ordered number mapping 
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            le.fit(week_day)
            y_(f" -  날짜에서 요일을 추출한뒤 수치형 라벨로 인코딩 합니다.(숫자순서랜덤.) ")
            print(f" - {dict(zip(le.transform(le.classes_),le.classes_))}")
            
            result_train=pd.concat([date_formated,
                                    pd.Series(date_formated.dt.year, name= 'year'),
                                    pd.Series(date_formated.dt.month, name= 'month'),
                                    pd.Series(date_formated.dt.day, name= 'day'),
                                    pd.Series(le.transform(week_day),name = 'week_day'),
                                    date_train],axis=1)
        
        result_train = result_train.drop([date_colname,'date_formated'],axis =1)
        yd(" - Result DataFrame added numeric day elements",(result_train))
        
        return result_train
    else:
        print(" - 날짜형 데이터가 없거나 있어도 변환하지 않게 설정되어있습니다.")
        return train_x

## 2-0 : [EDA] DATETIME -> year,mont,day, weekday graph visualizaiton
def step_2_0_EDA_Date_time_Statistic(train,target):
    import matplotlib.pyplot as plt, seaborn as sns
    """ 
    # #1. DATETIME -> year,mont,day, weekday graph visualizaiton
    # #2. Grouped by Day target mean distplot graph
    # #3. Day
    ## step_2_0_EDA_Date_time_Statistic(train,target)
    """
    # 10. mean(number of rentals) for year 
    y_(" - YEAR STAT")
    train.groupby('year').mean()[[target]].plot(figsize=(15,5))
    plt.show()

    # 11. mean(number of rentals) for month
    y_(" - MONTH STAT")
    train.groupby('month').mean()[[target]].plot(figsize=(15,5))
    plt.show()

    # 12. mean (target) for days
    y_(" - DAY STAT")
    train.groupby('day').mean()[[target]].plot(figsize=(15,5))

    plt.show()

    # etc
    week_stat =train.groupby('week_day').mean()[[target]]
    map_index = {0: 'Friday', 1: 'Monday', 2: 'Saturday', 3: 'Sunday', 4: 'Thursday', 5: 'Tuesday', 6: 'Wednesday'}
    week_stat = week_stat.rename(index=map_index)
    week_stat.plot(figsize= (15,5))
    y_(" - WEEKDAY STAT")
    plt.show()
    
    # 8 Year and Rental 
    month_day = train['month'].astype(str)+ "_"+ train['day'].astype(str)
    y_(" - YEAR(HUE)  vs TARGET STAT")
    plt.figure(figsize =(15,8))
    sns.scatterplot(x = month_day, y= train[target], hue =train['year'], s = 150)
    plt.xticks(rotation = 45, fontsize =5)
    plt.xlabel("Month _ day")
    plt.title(f" Yearly {target} count compare",fontsize =30)
    plt.show()

## 2-0 : [FE] DATETIME -> target adjusted inflation ratio
def step_2_FE_Inflation_adjustment(train, target,test):
    """
    # # When the target Increasing by year, target should be  adjusted inflation ratio!
    ## train, test = step_2_FE_Inflation_adjustment(train, target, test)
    """
    import pandas as pd
    print(r_cy("\n======================= step_2_FE_Inflation_adjustment ======================="))

    from sklearn.linear_model import LinearRegression
    # 종속변수와 독립변수를 분할하여 train_x, train_y 를 생성
    train_x,train_y,test_x= step_2_1_Indep_dep_val_split(train,test,target_colname= target, drop_test ="")

    model = LinearRegression()
    model.fit(train_x,train_y)
    predict = model.predict(test_x)  
    
    years =train['year'].value_counts().sort_index().index.tolist()
    y_(f" train years has range of {str(years)}")
    
    y_sum_target = {}
    ## train 에 있는 연도 데이터 저장. 
    for year in years:
        y_sum_target[f'sum_{year}'] = sum(train[train['year']==year][target])
    ## 다음년도 생성
    years.append(years[-1]+1) ## 다음년도 생성. 
    last_year = years[-1]
    y_sum_target[f'sum_{last_year}']= sum(predict)

    diff_last_year ={}
    
    for i in range(len(years)):
        if i == len(years):
            print()
        elif i == 0:
            print()
        else :
            diff_last_year[f"{last_year}/{years[i-1]}"]=y_sum_target[f"sum_{last_year}"]/y_sum_target[f"sum_{years[i-1]}"]
    # for i in diff_last_year.keys():
    #     print("rate of",i,diff_last_year[i])
            
    inf_adj_train_dict ={}
    y(f" - {last_year} based Inflation ratios :")
    for idx,ratio in enumerate(diff_last_year.keys()):
        ratio_rounded=round(diff_last_year[ratio],2)
        print(r_orange(f" ● {years[idx]}'s Inflation ratio :{ratio_rounded}"))

        inf_adj_train_dict[f'{years[idx]}']= train[train['year']==years[idx]][target]* ratio_rounded

    for order,i in enumerate(inf_adj_train_dict.keys()):
        idf=pd.Series(inf_adj_train_dict[i], name='inflation_target')
        if order ==0:
            new = idf
        else:
            new = pd.concat([new,idf], axis=0)
    yd("Inflation Target column result ",pd.DataFrame(new))
    y_(" - train 에 inflation target 을 추가합니다. ")
    y_(" - test 는 다음 년도 이므로 inflation rate =1  predict 과 같은 값으로 칼럼추가 ")
    test['inflation_target'] = predict
    return pd.concat([train, pd.DataFrame(new)], axis = 1),test

## 2-0 : [EDA] LatLng -> 위도 경도 지도에 표시 
def step_2_0_EDA_LocationData(train, latlng_cols =['next_latitude', 'next_longitude'],
                              line_print =False,dot_print = True  ):
    """
    # # [EDA] LatLng -> 위도 경도 지도에 표시 
    ##step_2_0_EDA_LocationData(train, latlng_cols =['next_latitude', 'next_longitude'], line_print =False,dot_print = True)
                             
    """
    print(r_cy("\n======================= step_2_0_EDA_LocationData ======================="))
    import folium 
    # coordinate info
    locations = train[latlng_cols][:10].values.tolist()
    center = train[latlng_cols][:10].mean().values.tolist()

    y(f" - map center :{str(center)}")
    m = folium.Map(location =center, zoom_start=13, titles ='cartodbpositron')

    if dot_print:
        # dot printing 
        for i , location in enumerate(locations):
            folium.Circle(
                radius = 50,
                location = location,
                tooltip = train['next_station'].loc[i],
                fill=True
            ).add_to(m)
    ## line printing 
    if line_print:
        folium.PolyLine(locations = locations).add_to(m)
    return m


## 2-0 : [FEATURE ENGINEERING CASE.4] 모든 feature 상호간 곱하거나 자신을 제곱하여 칼럼을 추가한다. 
def step_2_0_FE_polinomial_cols(train_x):
    """
    # #[FE 4] 모든 feature 상호간 곱하거나 자신을 제곱하여 칼럼을 추가
    ## train_x= step_2_0_FE_polinomial_cols(train_x)
    """
    y_(" - 두변수간 곱한 칼럼을 생성합니다. ")
    col_list = train_x.columns
    # 이중 for문을 사용하여 변수 자기 자신의 제곱과 두 변수간의 곱이라는 새로운 변수를 추가합니다.
    for i in range(len(col_list)):
        for j in range(i, len(col_list)):
            train_x[f'{col_list[i]}*{col_list[j]}'] = train_x[col_list[i]] * train_x[col_list[j]]
    return train_x

## [EDA] 2~3차 항이 있을때 target 에 대한 상관계수가 달라지는 지확인한다. 
def step_2_EDA_if_poly_top_corr_list(train,target,deg3=False):
    """ 
    # # 2~3차 항이 있을때 target 에 대한 상관계수가 달라지는 지확인한다. 
    ## step_2_EDA_if_poly_top_corr_list(train,target,deg3=False)
    """
    from sklearn.preprocessing import PolynomialFeatures
    import pandas as pd
    
    if deg3:
        poly = PolynomialFeatures(degree=3)
    else:
        poly = PolynomialFeatures(degree=2)   
    train_= train.drop("ID",axis=1)
    X_poly = poly.fit_transform(train_)
    corr_table =pd.DataFrame(X_poly,columns =poly.get_feature_names_out()).corr()
    aa=abs(corr_table[target].sort_values(ascending=False))>0.4
    col_list=corr_table[target].sort_values(ascending=False)[aa].index.tolist()
    colist  = [i for i in col_list if "target" not in i ]
    display(corr_table[target].sort_values(ascending=False)[colist])

##  [EDA]Feature IMportance EDA in DT    
def step_2_0_EDA_DTregressorImportance(train_x,train_y):
    """ 
    # # Feature IMportance Check EDA in DT    
    ## step_2_0_EDA_DTregressorImportance(train_x,train_y)
    """
    
    import pandas as pd
    from sklearn.tree import DecisionTreeRegressor
    model_dt = DecisionTreeRegressor(random_state =42)
    model_dt.fit(train_x,train_y)
    ## feature importance extraction
    feature_importances_dt = model_dt.feature_importances_
    # feature importance feature 별 visualization
    df_feature_importances_dt = pd.DataFrame({'Feature': train_x.columns, 'Importance': feature_importances_dt})
    sorted_df_feature_importances_dt= df_feature_importances_dt.sort_values(by='Importance',ascending=False).reset_index(drop=True)
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize= (8,4))
    ax.bar(train_x.columns, feature_importances_dt, color = 'skyblue')
    ax.set_xlabel("Feature")
    ax.set_ylabel("Feature Importance")
    ax.set_title("Feture importance in Decision Tree model")
    plt.tight_layout()
    plt.show()

##  [EDA]Feature IMportance EDA in Linear Regression  
def step_2_0_EDA_LinearRegressorImportance(train_x, train_y):
    """
    # #[EDA]Feature IMportance EDA in Linear Regression
    ## step_2_0_EDA_LinearRegressorImportance(train_x, train_y)
    """
    ## linear model 에서의 중요도 체크 
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression 

    # feature scaling 
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(train_x)

    # scaling 된 데이터로 학습. 
    model_lr_scaled = LinearRegression()
    model_lr_scaled.fit(X_scaled, train_y)

    # feature 가중치를 feature 중요도로 사용 
    feature_importances_lr = abs(model_lr_scaled.coef_)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize= (8,4))
    ax.bar(scaler.get_feature_names_out(), feature_importances_lr, color ="skyblue")
    ax.set_xlabel('Feature')
    ax.set_ylabel("Feature Importance")
    ax.set_title("Feature Importance in LinearREgression Model ")
    plt.tight_layout()
    plt.show()

## 2-0 [FE] FEature Generation( 범주형 피쳐 생성. )
def step_2_0_FE_Qcut_binning_categorize(train_x,train_y,test_x, col,target, q_=6):
    """
    # # 등빈도 binning[FE] FEature Generation( 범주형 피쳐 생성. )
    ## train= step_2_0_FE_Qcut_binning_categorize(train,"HouseAge",target ,q_=6)
    """
    import pandas as pd
    # train_q = train_x.copy()
    # train_q[f"{col}_cat"] = pd.qcut(train_q[col],q =q_)

    q_ = 6 # 6개의 구간으로 나눕니다.
    train_x[col + '_cat'], bins = pd.qcut(train_x[col], q=q_, labels=False, retbins=True, duplicates='drop')
    # qcut_bins[col] = bins # bins (구간 경계)를 저장합니다.

    # test_x에 train_x에서 얻은 bins를 이용하여 qcut 적용
    test_x[col + '_cat'] = pd.cut(test_x[col], bins=bins, labels=False, include_lowest=True, duplicates='drop')

    # 생성된 범주 확인 
    train_q_col = train_x[col].value_counts().sort_index()
    # yd(f"{col}_cat 생성",train_q_col)
    import seaborn as sns
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize= (8,4)) # 그림 크기 설정

    # 상자 수염 그림 생성, 축(ax) 지점
    sns.boxplot(x= f'{col}_cat', y =target, data = pd.concat([train_x,train_y],axis=1), ax= ax, palette='rainbow')
    plt.show()
    return train_x, test_x

## 2 : 데이터 종속 독립 분리
def step_2_1_Indep_dep_val_split(train,test,target_colname= 'target', drop_test =""):
    """
# # Independent Variables(train_x) and Dependeant Variable(train_y) SPLIT
## train_x,train_y,test_x=  step_2_1_Indep_dep_val_split(train,test,target_colname= target, drop_test ="")
    """
    print(r_cy("\n======================= step_2_1_Indep_dep_val_split ======================="))
    y(" - 독립변수와 종속 변수 분할 결과 ")
    if drop_test in train.columns.tolist():
        print(red(f' train 에서 {drop_test}을 삭제게합니다.' ))
        train_x = train.drop([drop_test,target_colname], axis =1)
        test_x = test.drop([drop_test], axis= 1)
    else : 
        train_x = train.drop([target_colname], axis =1)
        test_x = test
    train_y = train[target_colname]
    
    print(yellow(f" - 독립변수 (feature :{len(test_x.columns.tolist())}) : {test_x.columns.tolist()}"))
    print(yellow(f" - 종속변수 ({target_colname}) : rows-> ({len(train_y)})"))
    
    return train_x,train_y,test_x

## 2-1 : 분리된 독립변수 들에 MinMax scaling 적용하기 
def step_2_1_FE_MinMaxScaing(train_x, test_x):
    """
    # # MinMax scaling(정규화) 적용[0~1]
    ## train_x, test_x = step_2_1_FE_MinMaxScaing(train_x, test_x)
    """
    print(r_cy("\n======================= step_2_1_FE_MinMaxScaing ======================="))
    start_time = record_processing_time(start=True)

    import pandas as pd
    from sklearn.preprocessing import MinMaxScaler
    scaler= MinMaxScaler()
    scaler.fit(train_x)

    train_x_sc = pd.DataFrame(scaler.transform(train_x), columns=scaler.get_feature_names_out())
    test_x_sc = pd.DataFrame(scaler.transform(test_x), columns=scaler.feature_names_in_)
    yd("MINMAX SCALED TRAIN RESULT ",train_x_sc)
    yd("MINMAX SCALED TEST RESULT ",test_x_sc)
    record_processing_time(end=True, started_time= start_time)
    return train_x_sc, test_x_sc    

## 2-1 : 정규 스케일링
def step_2_1_FE_MissingValueProcess(train,test,missing_col, type ="to_mean", zero_mean_nan=True):
    """
    # # Missing Value Process 
    ## train,test = step_2_1_FE_MissingValueProcess(train,test,missing_col, type ="to_mean", zero_mean_nan=True)
    """
    print(r_cy("\n======================= step_2_1_FE_MissingValueProcess ======================="))
    import numpy as np, pandas as pd
    if type=='to_mean' and zero_mean_nan:
        y(f" - Missing value col {missing_col} transform as mean value ")
        for col in missing_col:
            mean_val = train[col].replace(0,np.nan).mean()
            train[col] = train[col].replace(0,mean_val)
            test[col]= test[col].replace(0,mean_val)
    
    return train,test

## 2-1 :표준 스케일링
def step_2_1_FE_StandardScaling(train_x,test_x):
    """
    # # Standard scaling(표준정규화) 적용
    ## train_x, test_x = step_2_1_FE_StandardScaling(train_x, test_x)
    """
    import pandas as pd
    from sklearn.preprocessing import StandardScaler
    print(r_cy("\n======================= step_2_1_FE_MinMaxScaing ======================="))
    start_time = record_processing_time(start=True)
    
    scaler= StandardScaler()
    scaler.fit(train_x)

    train_x_sc = pd.DataFrame(scaler.transform(train_x), columns=scaler.get_feature_names_out())
    test_x_sc = pd.DataFrame(scaler.transform(test_x), columns=scaler.feature_names_in_)
    yd("MINMAX SCALED TRAIN RESULT ",train_x_sc)
    yd("MINMAX SCALED TEST RESULT ",test_x_sc)
    record_processing_time(end=True, started_time= start_time)
    return train_x_sc, test_x_sc 

## 2-1 : 검증데이터 셋 만들기
def step_2_1_tr_te_split_(train_x,train_y, ts=0.3,rs=42):
    """" 
# #검증데이터 셋 만들기 
## X_train,X_valid, y_train,y_valid =step_2_1_tr_te_split_(train_x,train_y,ts=0.3,rs=42)    
    """
    from sklearn.model_selection import train_test_split 
    X_train,X_valid, y_train,y_valid=train_test_split(train_x, train_y, test_size= ts, random_state=rs)
    y_(" ** TRAIN TEST SPLIT INFO **")
    print(green(" - X_train:"),X_train.shape)
    print(green(" - X_valid:"),X_valid.shape)
    print(green(" - y_train:"),y_train.shape)
    print(green(" - y_valid:"),y_valid.shape)
    return X_train,X_valid, y_train,y_valid


## 3-0 : 수치형, 범주형 포괄 분포확인
def step_3_0_dataInfo2(df, replace_Nan=False, PrintOutColnumber = 0,nanFillValue=0, graphPlot=False):
    """
        3. 수치형 칼럼과 범주형 칼럼을 분류하기 위해서 칼럼분포를 시각화(hist, boxplot) 하고 수치형데이터 의 분포와 왜도확인: 
    >>  step_3_0_dataInfo2(df), 
    >>  step_3_1_numeric_column_dist_boxplot(train_x)
    >>  step_3_2_Skewness_check(train) 
    """
    g("4. Data inforamtion check")
    import warnings ;warnings.filterwarnings('ignore')
    ### Description  : 새운 데이터 정보 까기 함수
    import pandas as pd
    column_count = len(df.columns)
    row_count = len(df.index)
    nul_count  = df.isnull().sum().sum()
    value_kind_limit =10
    under_limit_columns =[]
    if PrintOutColnumber ==0 :
        PrintOutColnumber = column_count
    print(yellow(f" ◎ Column  : {column_count} 개 "))
    for num,i in enumerate(df.columns.tolist()):
        if num%5 != 0: 
            print(r_orange(f"   {i}"), end=", ")
        else:
            print(r_orange(f"\n   {i}"), end=", ")
    else:print("")
    print(yellow(f" ◎ Row size    : {row_count} 개"))
    print(yellow(f" ◎ Null count   : {nul_count} 개"))
    
    
    for idx, col in enumerate(df.columns):
        if df[f"{col}"].isnull().sum():
            print(f"   => {idx}번째.[{col}]컬럼 : ",f"null {df[f'{col}'].isnull().sum()} 개,\t not null {df[f'{col}'].notnull().sum()} 개")
            ## Null data fill
            if replace_Nan : ## nan 을 0 으로 대체 
                df[col].fillna(value=nanFillValue, inplace=True)  
    print(yellow(" ◎ 칼럼별 데이터 중복체크"))

    for idx, col in enumerate(df.dtypes.keys()):
        value_counts = df[col].value_counts()
        under_limit_columns.append(col)
        print(yellow(f"   □ {idx+1}번째 칼럼 \" {col}\"  타입 {df.dtypes[col]})"),\
                        red(f"\n    {len(df[col].unique())}"),\
                        green(f"\t/{len(df[col])} ")+ "\t[uniq/raw]",\
        )
        
        ### Value count 값 분포 확인
        check_df = pd.DataFrame(
                {
                    f'\"{col}\" 칼럼의 중복값': value_counts.index.tolist(),
                    '개수분포': value_counts.values.tolist()
                },
                index=range(1, len(value_counts) + 1)
)

        gd("","- Column values dist ",check_df.head(5))
        
        # 그래프 생성
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        if len(check_df.index) <10 :
            plt.figure(figsize=(6, 4))  # 그래프 크기 설정
            labels = value_counts.index.tolist()
            for i, label in enumerate(labels):
                # label을 문자열로 변환
                label = str(label)
                if len(label) > 10:
                    labels[i] = label[:10] + "..."
            colors = sns.color_palette("pastel", len(value_counts.values)) 
            # 퍼센트와 실제 수치 함께 표시
            def make_autopct(values):
                def my_autopct(pct):
                    total = sum(values)
                    val = int(round(pct * total / 100.0))
                    return f'{pct:.1f}% ({val:d})'
                return my_autopct

            plt.pie(value_counts.values, labels=labels, autopct=make_autopct(value_counts.values), startangle=90, colors=colors)
            plt.title(f"{col} 컬럼 값 분포 (파이 차트)", fontsize=13)
            plt.axis('equal')  # 파이 차트를 원형으로 유지
            plt.show()  # 그래프 출력
            if graphPlot : column_hist(df,col)
        else:
            plt.figure(figsize=(8, 3))  # 그래프 크기 설정
            # sns.barplot(x=value_counts.index, y=value_counts.values, palette="viridis") 
            sns.distplot(x=value_counts) 
            plt.title(f"{col} 컬럼 값 분포",fontsize=13)  # 그래프 제목 설정
            # x축 레이블 길이가 10 글자 이상이면 ...으로 표현
            for label in plt.gca().get_xticklabels():
                label = str(label)
                if len(label) > 10:
                    label = label[:10] + "..."  # 변경
                    # label.set_text(label[:10] + "...")
            plt.ylabel("개수")  # y축 레이블 설정
            plt.xticks(rotation=45)  # x축 레이블 회전
            plt.tight_layout()  # 레이블 간 간격 조정
            plt.show()  # 그래프 출력
            if graphPlot : column_hist(df,col)

    else: 
        print(red("\t[RESULT]"),"🙀🙀🙀"*10)
        print(yellow(f"\t🟦{value_kind_limit}개이하의 값 종류를 가지는 칼럼 "))
        # print(red(str(under_limit_columns)))
        for col in under_limit_columns:
            print("\t\t-",yellow(f"{col}:{len(df[col].unique())}: {df[col].unique().tolist()}"))
        else:
            
            print("\t",red(f"총 {len(under_limit_columns)}개"))
            print(r_cy(" ---- data frame 의 정보 조사 완료 -----}",True))
            return under_limit_columns
## 3-1 : 수치형 데이터 분포확인
def step_3_1_numeric_column_dist_boxplot(train_x):
    """
        3. 수치형 칼럼과 범주형 칼럼을 분류하기 위해서 칼럼분포를 시각화(hist, boxplot) 하고 수치형데이터 의 분포와 왜도확인: 
    >>  step_3_0_dataInfo2(df), 
    >>  step_3_1_numeric_column_dist_boxplot(train_x)
    >>  step_3_2_Skewness_check(train) 
    """
    g("3. train data 수치형 칼럼의 분포 확인")
    import matplotlib.pyplot as plt , seaborn as sns
    plotSetting()
    import pandas as pd
    numeric_col = train_x.select_dtypes(include ='number').columns.tolist()
    for feature in numeric_col:
        plt.figure(figsize = (8,3))
        plt.subplot(1,2,1)
        sns.histplot(train_x[feature], kde = True, color= 'skyblue')
        plt.title(f"Distribution of {feature} ")
        plt.subplot(1,2,2)
        sns.boxplot(y = train_x[feature])
        plt.title("Boxplot of "+ feature)
        plt.show()
    ## 3 : 수치형 데이터의 왜도 확인
## 3-2 : 수치형 데이터의 칼럼별 왜도확인
def step_3_2_Skewness_check(train, disp=True):

    """
    # # Numeric type features dist. and skewness check
    ##  stardardized_cols = step_3_2_Skewness_check(train_x) 
    """
    print(r_cy("\n======================= step_3_2_Skewness_check ======================="))
    import pandas as pd
    from IPython.display import display
    y_(" - Numeric cols' skewness check")
    skewness = train.select_dtypes("number").skew()
    
    df  =pd.DataFrame(skewness)
    med_skew =pd.DataFrame(df[(df[0].abs()>=0.5) & (df[0]<=1)].values, columns=["조금 높음(0.5~1)"], index=df[(df[0].abs()>=0.5) & (df[0]<=1)].index)
    high_skew =pd.DataFrame(df[(df[0].abs()>=1)].values, columns=["매우 높음(0.5~1)"],index=df[(df[0].abs()>=1)].index)
    no_skew =pd.DataFrame(df[(df[0].abs()<0.5)].values, columns=["왜도 없음"],index=df[(df[0].abs()<0.5)].index)
    
    if disp:
        display(pd.concat([no_skew,med_skew,high_skew], axis=1))
    
    stardardized_cols = no_skew.index.tolist()+med_skew.index.tolist()
    y_(f" - 정규적 칼럼(왜도<0.5) :{str(stardardized_cols)}")
    
    return stardardized_cols
    
## 4 : 타겟 데이터 균일도 확인
def step_4_MLOutput_target_ratio(train, target_col="Outcome",graph_show=False):
    """
    # #4. Target 값의 분포를 확인하여 데이터의 균일도를 확인합니다.(이진분류 타겟일 경우 적용)
    ## step_4_MLOutput_target_ratio(train_x, target_col=target,graph_show=False)
    """
    print(r_cy("\n======================= step_4_MLOutput_target_ratio ======================="))
    g("4. Output Target Ratio Check")
    ### Target 변수 class 별 갯수 및 비율 구하기 ( outcome 이 0 아니면 1일때 만 사용가능 )
    target_counts = train[target_col].value_counts()
    target_ratio = train[target_col].value_counts(normalize=True)
    # print(yellow(f"target_counts ['0'] = {target_counts[0]}  target_counts ['1'] = {target_counts[1]}"))
    # print(yellow(f"target_ratio ['0'] = {round(target_ratio[0]*100,2)} %  target_ratio ['1'] = {round(target_ratio[1]*100)} %"))
    
    for value in target_counts.index:
        print(blue("--" * 20))
        print(r_g(f"{value}:"))
        print(yellow(f"  Target Counts : {target_counts[value]} 개"))
        print(yellow(f"  Target Ratio : {round(target_ratio[value]*100, 2)}%"))
        print(blue("--" * 20))
    if graph_show:
        import matplotlib.pyplot as plt
        import seaborn as sns

        #  target ratio 계산
        target_ratio = round(train[target_col].value_counts(normalize=True) * 100, 2)

        plt.figure(figsize=(6,4))
        ax = sns.countplot(x=target_col, data=train,palette='viridis')
        print(r_g("--Target --",True))
        print(r_g("""  ** data 의 불균형을 확인하세요! 50:50 이 아니면 더 많은 쪽에 편향되어 학습됩니다. (편향시-> oversampling, undersampling,SMOTE)
                        """))
        
        # Annotate the bars with the percentage values
        for i, patch in enumerate(ax.patches):
            height = patch.get_height()
            ax.text(patch.get_x() + patch.get_width() / 2.,
                    height*1,
                    '{:.2f}%'.format(target_ratio[i]),
                    ha="center")

        plt.show()
        

        feature=train.drop(columns=target_col)
        numeric_features=feature.select_dtypes(include=['number']).columns.tolist()
        plt.figure(figsize=(10,6))
        print(r_g("--Features --",True))
        # print(red("  ** data 의 불균형을 확인하세요!"))
        for idx, feature in enumerate(numeric_features):
            ax1 = plt.subplot(3,3,idx+1)
            plt.title(feature)
            plt.tight_layout()
            sns.histplot(x=feature, data = train,kde=True,ax=ax1)

        plt.show()
    # df_display_centered(target_ratio)
## 4-1 : ROS 와 SMOTE 를 활용한 오버샘플링 -> 데이터 균일화 
def step_4_1_Oversampling(train_x,train_y, ros =False, smote =False,feature_select=[]):
    """
    #1.     
    ## train_x_ros, train_y_ros= step_4_1_Oversampling(train_x,train_y, ros=True)
    ## step_4_MLOutput_target_ratio(pd.concat([train_x_ros, train_y_ros],axis=1), target_col=target,graph_show=False)
    #2.
    ## train_x_smote, train_y_smote  = step_4_1_Oversampling(train_x,train_y, smote=True,feature_select=[])
    ## step_4_MLOutput_target_ratio(pd.concat([train_x_smote, train_y_smote],axis=1), target_col=target,graph_show=False)

    """
    print(r_cy("\n======================= step_4_1_Oversampling ======================="))
    import pandas as pd
    if ros:
        from imblearn.over_sampling import RandomOverSampler
        ros = RandomOverSampler(random_state= 42)
        X_resampled, y_resampled = ros.fit_resample(train_x,train_y)

        #결과 
        print(red(" - Random Over Sampling 을 적용하여 불균일을 처리합니다"))
        train_resampled = pd.concat([X_resampled,y_resampled],axis =1)
        return X_resampled, y_resampled 
    if smote:
        from imblearn.over_sampling import SMOTE
        smote = SMOTE(random_state =42)
        X_smote, y_smote =smote.fit_resample(train_x,train_y)
        # SMOTE 결과 
        print(red(" - Synthetic Minority OverSampling Technique(smote )을 적용하여 불균일을 처리합니다"))
        train_smote = pd.concat([X_smote, y_smote ],axis =1)
        
        import matplotlib.pyplot as plt, seaborn as sns
        import warnings ; warnings.filterwarnings('ignore')
        plotSetting()
        ## 피처 선택 
        if len(feature_select) !=0:
            feature1= feature_select[0]
            feature2=feature_select[1]
        else:
            feature1 = train_x.columns[0] #'이전 거래와의 시간 간격'
            feature2 =  train_x.columns[1] #'거래 금액'
        # 원본 데이터 분포 시각화 
        plt.figure(figsize= (16,5))
        plt.subplot(1,2,1)
        sns.scatterplot(x = train_x.loc[:,feature1], y = train_x.loc[:,feature2], hue =train_y)
        plt.title("Original Data")
        
        # SMMOTE 방법으로 오버샘플링 데이터 시각화 
        plt.subplot(1,2,2)
        sns.scatterplot(x = X_smote.loc[:,feature1], y  = X_smote.loc[:,feature2], hue= y_smote)
        plt.title("SMOTE oversampled DATA")
        plt.show()
        return X_smote, y_smote 
## 4-2: RUS 와 NearMiss 를 활용한 언더셈플링 = 데이터 균일화
def step_4_2_UnderSampling(train_x, train_y, rus =False, Nearmiss=False, f12=[]):
    """
1. Random under
train_rus= step_4_1_Oversampling(train_x,train_y, russ=True)
step_4_MLOutput_target_ratio(train_ros, target_col=target,graph_show=False) 
2. Near Miss
train_x_nearmiss,train_y_nearmiss= step_4_2_UnderSampling(train_x,train_y, Nearmiss=True)
step_4_MLOutput_target_ratio(train_rus, target_col=target,graph_show=False) 
    """
    import pandas as pd 
    if rus :
        from imblearn.under_sampling import RandomUnderSampler 
        
        rus = RandomUnderSampler(random_state = 42)
        X_rus, y_rus = rus.fit_resample(train_x, train_y)
        #결과 
        print(red(" - Random Under Sampling 을 적용하여 불균일을 처리합니다"))
        train_rus = pd.concat([X_rus, y_rus],axis =1)
        return train_rus
    if Nearmiss:
        from imblearn.under_sampling import NearMiss
        # NearMiss version 별 적용
        nm1 = NearMiss(version =1)
        nm2 = NearMiss(version =2)
        nm3 = NearMiss(version =3)
        
        X_nm1, y_nm1 = nm1.fit_resample(train_x, train_y)
        X_nm2, y_nm2 = nm2.fit_resample(train_x,train_y)
        X_nm3, y_nm3 = nm3.fit_resample(train_x, train_y)
        
        # 결과 출력 
        print(red(" - Random Under Sampling 을 적용하여 불균일을 처리합니다"))
        print("NearMiss -1 적용후 클래스 분포 \n", y_nm1.value_counts())
        print("NearMiss -2 적용후 클래스 분포 \n", y_nm2.value_counts())
        print("NearMiss -3 적용후 클래스 분포 \n", y_nm3.value_counts())
        
        
        import matplotlib.pyplot as plt , seaborn as sns
        feature1 = '이전 거래와의 시간 간격'
        feature2 = '거래 금액'

        if len(f12) !=0 :
            feature1 = f12[0]
            feature2 = f12[1]
        else:
            feature1 = train_x.columns[0] #'이전 거래와의 시간 간격'
            feature2 =  train_x.columns[1] #'거래 금액'
        
        # 시각화 
        plt.figure(figsize= (16,5))
        # 원본 데이터 분포 시각화 
        plt.subplot(1,4,1)
        sns.scatterplot(x =train_x.loc[:,feature1], y = train_x.loc[:,feature2], hue = train_y)
        plt.title('Original Data')
        # NearMiss -1 데이터 시각화 
        plt.subplot(1,4,2)
        sns.scatterplot(x =X_nm1.loc[:,feature1], y = X_nm1.loc[:,feature2], hue = y_nm1)
        plt.title('NearMiss -1 Data')
        # NearMiss -1 데이터 시각화 
        plt.subplot(1,4,3)
        sns.scatterplot(x =X_nm2.loc[:,feature1], y = X_nm2.loc[:,feature2], hue = y_nm2)
        plt.title('NearMiss -2 Data')
        # NearMiss -1 데이터 시각화 
        plt.subplot(1,4,4)
        sns.scatterplot(x =X_nm3.loc[:,feature1], y = X_nm3.loc[:,feature2], hue = y_nm3)
        plt.title('NearMiss -3 Data')
        plt.show()
        
        train_rus = pd.concat([X_nm2, y_nm2],axis =1)
        
        return X_nm2, y_nm2



## 5-0: [EDA] 이상치 시각화 및 확인
def step_5_0_Outlier_check(train, target='income_total'):
    """
    # # Outlier of target column 
    ## outlier_value = step_5_0_Outlier_check(X_train, target=target)

    """
    print(r_cy("\n======================= step_5_0_Outlier_check ======================="))
    import matplotlib.pyplot as plt , seaborn as sns
    import numpy as np
    def out_zscore(data, threshold =3):
        mean = np.mean(data)
        std = np.std(data)
        zscores = [(x-mean)/std for x in data]
        outliers = [x for x in data if np.abs((x- mean)/std)> threshold]
        return zscores, len(outliers)
    zscores ,num_outliers = out_zscore(train[target])
    y(f" -  Outlier check in {target} column")
    plt.figure(figsize= (12,3))
    plt.boxplot(train[target], vert = False)
    plt.title(f"Boxplot for feature {target}")
    plt.show()
    
    y(" - Zscore :(X-m)/s) Dist Check (redline : z > 3)")
    plt.figure(figsize =(10,5))
    plotSetting()
    sns.distplot(zscores, color='red')
    plt.axvspan(xmin= 3, xmax = max(zscores), alpha =0.2, color= 'red')
    plt.title("Z-score dist & Outlier region(red)")
    plt.show()
    outlier_value=np.mean(train[target])+np.std(train[target])*3
    y_(f" - Total number of outliers are {num_outliers} : {target}> {outlier_value}")
    
    # 3. 운행 시간 분호 시각화 
    import matplotlib.pyplot as plt
    ax = train[target].plot(figsize=(20,10), alpha=0.6)    
    ax.set_title(f'{target}',fontsize= 30)    
    ax.set_xlabel('index')    
    ax.set_ylabel(f'{target}')    
    ax.hlines(y = min(train[target]), xmin=0, xmax=len(train), colors='red')    
    ax.hlines(y = outlier_value, xmin=0, xmax=len(train), colors='orange')    
    ax.hlines(y = outlier_value+( max(train[target])-outlier_value)*0.5, xmin=0, xmax=len(train), colors='blue')    
    ax.hlines(y = max(train[target])*0.8, xmin=0, xmax=len(train), colors='green')    
    plt.show()    
    y_(
    f""" - Horizontal line explaination
    • red line(min) : {min(train[target])}
    • orange line(outlier): {outlier_value}
    • blue line(out+alpha) :{outlier_value+( max(train[target])-outlier_value)*0.5,}
    • green line(max*0.8) :{max(train[target])*0.8}""")
    
    step_5_0_EDA_region_split_by_outlier(train,target,outlier_value)
    
   
    return outlier_value
## 5-0: [EDA] target dist hline split by outliers
def step_5_0_EDA_region_split_by_outlier(train,target,outlier_value):
    """
    # # Visualize the target number by regions of outlier and min max
    ##region_split_by_outlier(train,target,outlier_value)
    """
    import matplotlib.pyplot as plt
    outlier_value =int(outlier_value)
    reg_val = [ min(train[target])*2, outlier_value, outlier_value*2,max(train[target])*0.8]    
    regions ={}
    regions[f'A'] = train[train[target]<reg_val[0]]
    regions[f'B'] =train[(train[target]>=reg_val[0]) & (train[target]<reg_val[1])]
    regions[f'C'] =train[(train[target]>=reg_val[1]) & (train[target]<reg_val[2])]
    regions[f'D'] =train[(train[target]>=reg_val[2]) & (train[target]<reg_val[3])]
    regions[f'E'] = train[train[target]>reg_val[3]]

    x = [f'{reg_val[0]}미만', f'{reg_val[0]}~{reg_val[1]}', f'{reg_val[1]}~{reg_val[2]}',
        f'{reg_val[2]}~{reg_val[3]:.0f}', f'{reg_val[3]:.0f}이상']
    
    y = [len(regions[f'A']),
        len(regions[f'B']),
        len(regions[f'C']),
        len(regions[f'D']),
        len(regions[f'E'])]
    y_(f" - 'GRAPH : Number of {target} by Region'")
    # fig와 ax 객체 생성
    fig, ax = plt.subplots(figsize =(12,4),dpi=150)
    ax.bar(x,y)
    ax.set_title(f'Number of "{target}" by Region')
    ax.set_xlabel(f'{target}')
    ax.set_ylabel('Number')
    plt.show()
    
    y_(" - B / rest ratio pi plot & B histogram")
    label = ['B region', 'Rest']
    value = [len(regions[f'B'])/len(train), (1-len(regions[f'B'])/len(train))]
    plt.figure(figsize=(10,5))
    plt.subplot(1,2,1)
    plt.title(f'{target} 구간 비율')
    plt.pie(value, labels=label, colors=['orange','pink'], autopct='%1.1f%%', startangle=140)
    plt.legend()
    
    plt.subplot(1,2,2)
    import seaborn as sns
    sns.histplot(regions[f'B'][target], bins=20)
    plt.title('B region Hist')
    plt.xlabel(f'{target}')
    plt.ylabel('Number')
    plt.show()
    # plt.figure(figsize=(4,5))
    
    

    plt.show()

## 5-1 : [FE] 이상치 최빈값 변환
def step_5_1_Outlier_processing(df,colname,over_val=0,under_val=0, replace_outlier = 'mode'):
    """
    # # Outlier 를 확인(0),사용자기준으로 걸르고 최빈값으로 대체(1), zscore, IQR 값으로 확인후 제거(2) : 
        
    ## step_5_0_Outlier_check(X_train, col='income_total')
    ## train_x= step_5_1_Outlier_processing(train_x,'trestbps',over_val=170,under_val=0, replace_outlier = 'mode')
    ## X_train =  step_5_2_Outlier_erase(X_train, col='income_total', threshold = 3, IQR=True)

    """
    g("6. Outlier 최빈값 대체")
    import pandas as pd
    from IPython.display import display
    mode_value = df[colname].mode()[0] # 최빈값
    mean_value = df[colname].mean()
    if over_val!=0:
        y(f" - {colname}에서 outlier(over) 를 포함하는 data display")
        display(df.loc[df[colname]> over_val , colname])
        outlier_index = df.loc[df[colname]>over_val,colname].index
        # outlier ->Na 
        df.loc[df[colname]>over_val,colname] = pd.NA
        if replace_outlier =='mode':
            df[colname] = df[colname].fillna(mode_value)
            gd("",f" {colname} feature의 이상치 변환 ({over_val} => {mode_value}) 결과",df.loc[outlier_index])
        
    if under_val!=0:
        df[colname]<under_val
        y(f" -{colname}에서 outlier(under) 를 포함하는 data display")
        display(df.loc[df[colname] < under_val , colname])
        outlier_index = df.loc[df[colname]<under_val,colname].index
        # outlier ->Na 
        df.loc[df[colname]<under_val,colname] = pd.NA
        if replace_outlier =='mode':
            df[colname] = df[colname].fillna(mode_value)
            gd("",f" {colname} feature의 이상치 변환 ({under_val} => {mode_value}) 결과",df.loc[outlier_index])
    
    return df


## 5-2 : [FE]이상치 제거 (Zscore, IQR)
def step_5_2_Outlier_erase_Z_IQR(X_train, col='income_total', threshold = 3,scipy_use=False, Z_score =False, IQR =False):
    """
    # #[FE]이상치 제거 (Zscore, IQR)
    ## train_no_outlier =  step_5_2_Outlier_erase_Z_IQR(train, col=target, threshold = 3, scipy_use=False, Z_score =False, IQR =False)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= step_5_2_Outlier_erase_Z_IQR ======================="))
    from scipy import stats
    import matplotlib.pyplot as plt
    result  =0
    if Z_score:
        
        Z_train = X_train.copy()
        mean_train = Z_train[col].mean()
        std_train = Z_train[col].std()
        g(f" - Train 데이터의 평균 : {mean_train:.2f}, 표준편차 :{std_train:.2f}")
        g(f" - 임계값 설정 : threshold ={threshold}" )
        g(" - Train 데이터로 Z점수 계산 및 이상치 제거 ")
        Z_train[f'z_score_{col}'] = (Z_train[col] - mean_train)/std_train 
        if scipy_use :
            print(yellow(" -- zscore 를 직접계산합니다."))
            train_no_outliers = Z_scipy_train[Z_scipy_train[f'z_score_{col}'].abs() <=threshold]
            train_no_outliers = train_no_outliers.drop(f'z_score_{col}', axis =1)
        else:        
            print(yellow(" -- zscore 를 계산하기 위해 scipy stat 라이브러리를 사용합니다."))
            train_no_outliers = Z_train[Z_train[f'z_score_{col}'].abs() <=threshold]
            train_no_outliers = train_no_outliers.drop(f'z_score_{col}', axis =1)
        
        print(yellow(f" - train no outliers shape:  {train_no_outliers.shape}/ {X_train.shape}"))
        result = train_no_outliers
    elif IQR:
        print(yellow(" - InterQuantile Range 방식을 사용하여 이상치를 탐지합니다. "))
        Z_scipy_train  =X_train.copy()
        Z_scipy_train[f'z_score_{col}'] = stats.zscore(Z_scipy_train[col])
        Q1 = X_train[col].quantile(0.25)
        Q3 = X_train[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
       
        lower_outliers = X_train[X_train[col]< lower_bound]
        upper_outliers = X_train[X_train[col]> upper_bound]
        num_lower_outliers = len(lower_outliers)
        num_upper_outliers = len(upper_outliers)


         ## IQR values plot
        y_(f""" - Q1:{Q1:.2f}\n   - Q3:{Q3:.2f}\n   - IQR:{IQR:.2f}""")
        y_(f" - L-bound {lower_bound:.2f}({num_lower_outliers}개), U-bound : {upper_bound:.2f}({num_upper_outliers}개)")
        
        
        result = 0
        
        # y_(f" - quantile 함수를 활용한 IQR 이상치 제거 결과")
        train_no_outliers_iqr = X_train[(X_train[col] >= lower_bound) & (X_train[col]<=upper_bound)]
        y_(f" - rows: original({len(X_train)}) ->result_rows({len(train_no_outliers_iqr)})")
        g( "- 이상치 제거후 boxplot 확인 ")
        plt.figure(figsize = (7,3))
        plt.boxplot(train_no_outliers_iqr[col],vert=False)
        plt.title(f"Box plot for Featrue {col} (AFTER IQR outlier 제거)")
        plt.show()
        result = train_no_outliers_iqr
        
        def target_vs_fefatures_by_outlier(train,upper_bound,lower_bound):
            print(r_cy("\n======================= target_vs_fefatures_by_outlier ======================="))
            # 8.이상치 유무에 따른  target 과 feature 들의 평균 비교 
            y_("- 이상치 유무에 따른  target 과 feature 들의 평균 비교 ")
            import matplotlib.pyplot as plt
            fig =plt.figure(figsize=(20,10), dpi =100)
            

            lm_features = train.select_dtypes(include= 'number').columns.tolist()
            plot_rows_num = len(lm_features)//4 if len(lm_features)%4==0 else len(lm_features)//4+1
            axs = fig.subplots(plot_rows_num,4)

            이상치일경우높은수치를갖는칼럼 = []
            # print(lm_features)
            for order, feature in enumerate(lm_features):
                x = ['target < High', 'target > High']
                y_over_out = train[train[col] > upper_bound][feature].mean()
                y_under_out=train[train[col] <= upper_bound][feature].mean()
                ratio_ = 1.4
                if y_over_out> y_under_out*ratio_:
                    이상치일경우높은수치를갖는칼럼.append(feature)
                    
                    axs[row][column].bar
                y = [y_under_out,y_over_out]
                row = int(order/4)
                column = order%4
                bar_color = 'orange' if y_over_out > y_under_out * ratio_ else None 
                axs[row][column].set_title("target X "+ feature, fontsize= 20)
                axs[row][column].set_ylabel(feature+"의 평균", fontsize=21)
                axs[row][column].set_xticks([0,1])
                axs[row][column].set_xticklabels([x[0],x[1]],fontsize =18)
                axs[row][column].bar(x,y,color=bar_color)
                
                fig.tight_layout()
                
            plt.title("underlier vs overlier of feature")
            plt.show()
            y_(f" - 이상치일경우높은수치를갖는칼럼: {str(이상치일경우높은수치를갖는칼럼)}")
        target_vs_fefatures_by_outlier(X_train,upper_bound,lower_bound)        
                
        
    else: 
        y_(" Zscore 나 IQR 을 선택하세요")
        result  =0
    
    return result   
## 5-3 : [FE] DBSCAN 을 활용한 이상치 제거
def step_5_3_Outlier_erase_DBSCAN(X_train, 
                                col1='공복 혈당', col2='중성 지방',
                                db_eps = 0.5,
                                db_min_sample  =5,
                                all_case= False,
                                discret_type_col =['충치','요 단백'],
                                outlier_erase=False):
    """
    # #두개의 칼럼사이의 아웃라이어만 제거
    ## train_DBSCANed_= step_5_3_Outlier_erase_DBSCAN(
                            X_train,col1='공복 혈당', 
                            col2='중성 지방',
                            db_eps = 0.5,
                            db_min_sample  =5,
                            outlier_erase=True)
    # # 정규화 안되어있는 feature 에서 2개씩 뽑아서 아웃라이어 제거
    ## train_DBSCANed_=step_5_3_Outlier_erase_DBSCAN(
                            X_train,
                            db_eps = 0.5,
                            db_min_sample  =5,
                            all_case=True,
                            outlier_erase=True)
    """
    print(r_cy("\n======================= step_5_3_Outlier_erase_DBSCAN ======================="))

    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from itertools import combinations, permutations
    
    
    DBSCAN_train = X_train.copy()

    stardardized_cols= step_3_2_Skewness_check(DBSCAN_train)
    feature_columns = DBSCAN_train.columns.tolist() 
    feature_types = [(i,'Dis') if len(DBSCAN_train[i].value_counts().index) < 20 else (i,'Con') for i in feature_columns]
    y_(f" 이산형 features")
    dis_type_col =[]
    for i in feature_types:
        if i[1]=='Dis':
            print(yellow(f"  {i}"))
            dis_type_col.append(i[0])
            

    train_outliers=DBSCAN_train.drop(stardardized_cols, axis=1)
    outlier_col = [i for i in train_outliers.columns.tolist() if i not in dis_type_col]
    
    
    y_(f" - 아웃라이어 칼럼(이산변수제외) :{str(outlier_col)}")
    train_outliers = train_outliers[outlier_col]
    # df_display_centered(train_outliers.head(2))
    combi = list(combinations(outlier_col, 2))
    
    
    
    
    
    ## 데이터 표준화 
    def vis_DBSCAN(DBSCAN_train,col1,col2,):
        import matplotlib.pyplot as plt
        import seaborn as sns
        import pandas as pd
        from sklearn.cluster import DBSCAN
        from sklearn.preprocessing import StandardScaler
        y_(f" - {col1} vs {col2}  SCATTER")
        scaler = StandardScaler()
        data_scaled = pd.DataFrame(scaler.fit_transform(DBSCAN_train[[col1,col2]]),columns=[col1,col2])
        db_cluster = DBSCAN(eps =db_eps, min_samples=db_min_sample ).fit(data_scaled)
        labels = db_cluster.labels_
        
        cluster_sample =db_cluster.fit_predict(data_scaled)
        DBSCAN_train['clusters']= cluster_sample
        sample_no_outliers =DBSCAN_train[DBSCAN_train['clusters']!=-1]
        # yd("이상치가 아닌 데이터 ",sample_no_outliers)
        
        plt.figure(figsize= (10,6))
        plt.scatter(DBSCAN_train[col1],DBSCAN_train[col2], c=DBSCAN_train['clusters'],cmap='Set3',label='Clusters')
        plt.scatter(DBSCAN_train[DBSCAN_train['clusters']== -1][col1],
                    DBSCAN_train[DBSCAN_train['clusters']==-1][col2],
                    color ='red', label='outliers')
        
        plt.xlabel(col1,fontsize=10)
        plt.ylabel(col2,fontsize=10)
        plt.title(f"{col1}과 {col2}의 DBSCAN")    
        plt.legend()
        plt.grid(True)
        plt.show()
        return sample_no_outliers
    
    if all_case:
        y_(f" - 총 경우의 수({len(outlier_col)}C2):{len(combi)}")
        erased_outlier =[]
        for (x,y) in combi:
            sample_no_outlier = vis_DBSCAN(DBSCAN_train,x,y)
            if outlier_erase:
                print(yellow(f" -  {x} {y} 그래프에서 아웃라이어를 제거합니다."))
                erased_outlier.append(len(DBSCAN_train)-len(sample_no_outlier))
                print(f" - 이그래프로 제거한 아웃라이어수 : {len(DBSCAN_train)-len(sample_no_outlier)}")
                print(f" - 현재까지 DBSCAN으로 제거된 아웃라이어 수: {sum(erased_outlier)}")
                DBSCAN_train=sample_no_outlier
                
            else: print("아웃라이어를 제거하지 않습니다(보기용)")
        
        
        return DBSCAN_train  
    else:
        sample_no_outlier= vis_DBSCAN(DBSCAN_train,col1,col2)
        print(f" - 이그래프로 제거한 아웃라이어수 : {len(DBSCAN_train)-len(sample_no_outlier)}")
        return sample_no_outlier
    

## 6 : 수치형데이터의 정규화 
def step_6_Standardization(train_x,test_x,need_to_scale = ['age','trestbps','chol','thalach']):
    """
    6. 정규화 를 진행합니다. 
    >> train_x_scaled_df,test_x_scaled_df =  step_6_Standardization(train_x,test_x,need_to_scale = ['age','trestbps','chol','thalach'])
    """
    g(f"7. {need_to_scale} 칼럼의 정규화를 진행합니다 ")
    import pandas as pd
    import matplotlib.pyplot as plt, seaborn as sns
    from sklearn.preprocessing import StandardScaler
    
    scaler = StandardScaler()
    train_x_scaled = scaler.fit_transform(train_x[need_to_scale])
    test_x_scaled = scaler.transform(test_x[need_to_scale] )
    train_x_scaled_df = pd.DataFrame(train_x_scaled, columns =need_to_scale)
    test_x_scaled_df = pd.DataFrame(test_x_scaled, columns = need_to_scale)

    gd("","- 스케일링후 데이터 확인", train_x_scaled_df)
    for feature in train_x_scaled_df.columns:
        plt.figure(figsize = (8,3))
        plt.subplot(1,2,1)
        sns.histplot(train_x_scaled_df[feature], kde = True, color= 'skyblue')
        plt.title(f"Distribution of scaled {feature} ")
        plt.subplot(1,2,2)
        sns.boxplot(y = train_x_scaled_df[feature])
        plt.title("Boxplot of scaled"+ feature)
        plt.show()  
    return train_x_scaled_df,test_x_scaled_df

## 8 : 이상치 데이터 로그변환 
def step_8_Log_transform(train_x,test_x, need_to_log_trainsform='oldpeak'):
    """
    8. 로그 변환 이 필요한 데이터에 로그 변환을 진행합니다. : 
    >> train_x,test_x=  step_8_Log_transform(train_x,test_x, need_to_log_trainsform=['oldpeak'])
    """
    g(f"8.{need_to_log_trainsform} 칼럼의 Log 변환 을 진행합니다 ")
    
    import pandas as pd , matplotlib.pyplot as plt, seaborn as sns, numpy as np
    # zero_index = train_x.loc[train_x[need_to_log_trainsform]<=0,need_to_log_trainsform].index

    train_x.loc[train_x[need_to_log_trainsform]==0,need_to_log_trainsform] = pd.NA
    train_x[need_to_log_trainsform]=train_x[need_to_log_trainsform].fillna(0.0001)
    
    train_x[need_to_log_trainsform] =np.log(train_x[need_to_log_trainsform])
    test_x[need_to_log_trainsform] =np.log(test_x[need_to_log_trainsform])
    
    # display(test_x[need_to_log_trainsform].head())
    plt.figure(figsize=(6,3))
    plt.title(f"{need_to_log_trainsform} feature 의 log 변환후 분포")
    ax = sns.histplot(train_x[need_to_log_trainsform], kde= True, color = 'yellow')
    plt.show()
    
    return train_x, test_x

## 9 : 차원 축소 주성분 분석 PCA :SVD 수행 
def step_9_FE_PCA_svd(train_x,test_x,sklearn_use =True):
    """
    # # 주성분분석 
    ## train_pca, test_pca =step_9_FE_PCA_svd(train_x,test_x,sklearn_use =True)
    """
    print(r_cy("====================== step_9_FE_PCA_svd ======================"))
    import pandas as pd
    start_time =record_processing_time(start=True)
    
    if sklearn_use:
        scaled_train = train_x.copy()
        scaled_test = test_x.copy()
        from sklearn.decomposition import PCA

        pca = PCA(n_components = 3)
        pca.fit(scaled_train)

        train_pca = pca.transform(scaled_train)
        test_pca = pca.transform(scaled_test)
        yd(f" 각성 분 설명 비율 {pca.explained_variance_ratio_}", pd.DataFrame(train_pca),)
        record_processing_time(end=True, started_time= start_time)
        return train_pca, test_pca
    
    else:
        U, S, Vt = np.linalg.svd(train_x, full_matrices =False)
        ## 주성분 개수 설정 
        n_components = 3
        # n_components 에 해당하는 주성분만 선택 
        components_train = Vt[:n_components]
        ## 
        yd(" - [분산극대화 축 성분 행렬 추출] Vt of train_x(표준)",pd.DataFrame(Vt),heading=0)
        yd(" - [Top3 Comp extraction]  components train",pd.DataFrame(components_train))
        y( "- = lower dim data ")
        
        pca_train = np.dot(train_x, components_train.T)
        pca_test = np.dot(test_x, components_train.T)
        y_(f"[Data Projection] trainx dot producted bu Vt.head(3) \n >> pca_train: {pca_train.shape}, pca_test:{pca_test.shape}")
        record_processing_time(end=True, started_time= start_time)
        return pca_train,pca_test
    





############################################################################################################


## 기타
def key_selector(data_dict,num=0, file_list_show = False, df_info_show= False,df_graph_show=False):
    """
        - Description : data가 들어있는 dictionary 파일을 순서대로 선택해서 출력함 
            그리고 딕셔너리에 있는 df key 를 출력하고 사용자가 몇번째 데이터를 호출했는지 알려줌. 
        - 예시 : 
        - update 2024.09.11 AM 10:50 by pdg
            - 출력되는거 보기싫어서 기능 만듬. 
    """
    from IPython.display import display, HTML
    data_name= sorted(data_dict.keys())[num]
    i = num
    df = data_dict[data_name]
    data_num= sorted(data_dict.keys())[i]
    if df_info_show:
        print(green("◎  "+f"{data_num}"+"--"*(100-(len(data_num)//2)) ,True))
        print(r_g(f"-Data info : ",True))
        df.info()
        # 화면 가운데 정렬하여 출력
        print(yellow(f"-DataFrame.head : ",True))
        display(df.head(3))
        print(yellow(f"-DataFrame.tail : ",True))
        display(df.tail(3))
        print(yellow("-Random sample Watching(7) : ",True))
        display(df.sample(7))
        print(r_g(f"-DataFrame Describtion:",True))
        display(df.describe())
        if df_graph_show:
            plotSetting(pltStyle='default')
            step_3_0_dataInfo2( key_selector(data_dict,i))
        print(blue("--"*100))
    if file_list_show:
        for order,i in enumerate(sorted(data_dict.keys())):
            print(r_g(f"\t{order} 번째 : {i}"))
            print(r_g(f"\t{num}번째 데이터: {data_name} "))
                
    return data_dict[data_name]

### training Set Analysis Functions( 정리 필요)
def quantile_dist_for_binary_output(train, target_col="Outcome"):
    print(yellow("*이진 분류 output 일 경우에 한하여 모든 칼럼에서의 output 비율을 사분위 단위로 보는 히스토그램을 플랏합니다"))
    import matplotlib.pyplot as plt
    import numpy as np, seaborn as sns
    feature=train.drop(columns=target_col)
    numeric_features=feature.select_dtypes(include=['number']).columns.tolist()

    for selected_feature in numeric_features:
        # 사분위 수 계산
        q1 = np.percentile(train[selected_feature], 25)
        q2 = np.percentile(train[selected_feature], 50)
        q3 = np.percentile(train[selected_feature], 75)
        q4 = np.percentile(train[selected_feature], 100)
        q_lst = [ 0, q1, q2, q3, q4]
        # target class 1의 갯수 대비 target class 0의 갯수의 비율 구하기
        num_class0 = len(train [ train[target_col] == 0 ])
        num_class1 = len(train [ train[target_col] == 1 ])

        ratio_class1_class0 = num_class0 / num_class1

        # 히스토그램 그리기
        plt.figure(figsize=(8, 4))
        h0_ax1 = sns.histplot(data=train[train[target_col] == 0], x=selected_feature, bins = q_lst,  alpha=0.3,  label=f'{target_col} = 0: 정상', color='blue')  # Outcome = 0 컬러 변경
        h1_ax1 = sns.histplot(data=train[train[target_col] == 1], x=selected_feature, bins = q_lst,  alpha=0.3,  label=f'{target_col} = 1: 당뇨', color='orange') # Outcome = 1 컬러 변경

        # target 변수의 class가 1일 때의 각 bin의 높이(개수)와 경계값을 얻어옵니다
        h1_heights, h1_edges = np.histogram(train[train[target_col] == 1][selected_feature], bins=q_lst)

        # target class 1의 갯수 대비 target class 0의 갯수의 비율과 일치하는 각 구간의 수평선을 그린다
        for i in range(len(h1_heights)):
            plt.hlines(y=h1_heights[i] * ratio_class1_class0 , xmin=h1_edges[i], xmax=h1_edges[i+1], linestyles='solid', colors='red', alpha=0.5)  # 레전드 추가

        plt.gca().set_title(f"{selected_feature} (사분위 기준 분포)")
        plt.xlabel(f"{selected_feature}")  # x축 레이블 추가
        plt.ylabel("Count")  # y축 레이블 추가
        plt.legend(loc = 'best')  # 레전드 표시
        plt.tight_layout()
        plt.show()

def feeature_outlier_graph(train, target_col = "Outcome"):
    print(yellow("*이상치를 찾아보자"))
    import matplotlib.pyplot as plt
    import numpy as np, seaborn as sns
    feature=train.drop(columns=target_col)
    numeric_features=feature.select_dtypes(include=['number']).columns.tolist()
    plt.figure(figsize=(12,8))
    for idx, feature in enumerate(numeric_features):
        ax2 = plt.subplot(3,3,idx+1)
        plt.title(feature)
        plt.tight_layout()
        sns.boxplot(x=target_col, y=feature, data = train,palette='Set2', ax=ax2)

    plt.show()

def pairPlot_numeric_cols(train, target_cols = "Outcome"):
    print(yellow("* Pariplot 은 변수 쌍 간의 관계와 타겟 변수와의 연관성을 보아라."))
    print(yellow("  1. feature 간 강한 선형관계가 있는가? 있으면 다중공성선 문제 생김 -> 변수선택이나 차원축소 로 처리할것"))
    print(yellow("  2. 분리가능한 경계가 존재하는가? 경계가 명확한 feature 쌍은 성능향상에 도움이 된다.-> 두개로 조합된 범주형 feature 생성할것 "))
    print(yellow("  3. 이상치가 존재하는 쌍이 존재하는가? -> 이상치 전처리 , 특이한 패턴 잘볼것"))
    import matplotlib.pyplot as plt, seaborn as sns
    # plt.figure(figsize=(3,2))
    numeric_features=train.select_dtypes(include=['number']).columns.tolist()
    # features_to_analyze = ['Insulin', 'SkinThickness', 'Glucose', 'BMI', 'Outcome']
    sns.pairplot(train[numeric_features], hue=target_cols, palette="Set2")
    plt.show()
    
def drop_single_data_col(df):
    ## 데이터 종류가 하나뿐인 칼럼은 삭제하는 함수
    to_drop_columns = []

    for order,i in enumerate(df.columns):
        if len(df[i].unique())==1:
            print(yellow(f"   -{order}.{i}칼럼의 데이터는 하나뿐입니다."),rainbow_cyan(" 값:"),rainbow_orange(f"{df[i].unique()[0]}"))
            to_drop_columns.append(i)
    df = df.drop(columns = to_drop_columns)
    print(blue("--- 데이터가 하나뿐인 칼럼을 삭제한 데이터프레임"))
    return df

def data_fetch(data_folder_path,start,end):
    
    import os,pandas as pd
    from tqdm import tqdm  # 진행 상황 표시 라이브러리
    data_dict ={}
    count = 1
    
    def encoding_detector(file_path):
        import chardet ## encoding 정보 확인 라이브러리 
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)['encoding']
            print(blue(f"  - Detected encoding: {encoding}"))
            return encoding
    
    
    with tqdm(total=100, desc="Data File 불러오는 중..", bar_format="{desc}:{percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [elapsed: {elapsed} remaining: {remaining}]", colour='green') as pbar:
        for filename in os.listdir(data_folder_path):
            file_number = int(filename.split(".")[0])
            if file_number in range(start, end):
                file_path = os.path.join(data_folder_path, filename)
                encoding = encoding_detector(file_path)
                if filename.endswith(".csv"):
                    data_dict[filename] = pd.read_csv(file_path, encoding=encoding)
                elif filename.endswith((".xls", ".xlsx")):
                    data_dict[filename] = pd.read_excel(file_path)
                else:
                    print(f"Unsupported file type: {filename}")
                
                pbar.update(count)
                count += 3

    return data_dict

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

def column_hist(df,col):
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    num_cols = df.select_dtypes(include=np.number).columns  # 숫자형 칼럼만 선택

    if col in num_cols:
        plt.figure(figsize=(5, 4))
        # 히스토그램과 KDE 동시에 그리기
        sns.histplot(df[col], kde=True, bins=30)
        plt.title(f"{col} -Histogram", fontsize=15)
        plt.xlabel(col, fontsize=12)
        plt.ylabel("Density", fontsize=12)
            # 기술 통계치 계산
        mean_val = df[col].mean()
        median_val = df[col].median()
        std_val = df[col].std()
        min_val = df[col].min()
        max_val = df[col].max()

        # 그래프에 기술 통계치 추가
        stats_text = (
        
        f"""평균값 : {mean_val:<10.1f}
        중앙값 : {median_val:<10.1f}
        표준편차: {std_val:<10.1f}
        최소값 : {min_val:<10.1f}
        최대값 : {max_val:<10.1f}"""
        )
        
        # 텍스트 위치 조정 (좌하단)
        plt.text(x=0.95, y=0.95, s=stats_text, fontsize=8, 
                ha='right', va='top', transform=plt.gca().transAxes, 
                bbox=dict(facecolor='white', alpha=0.7))
        plt.show()
    else: 
        print(colored_text("숫자형데이터가 아닙니다",'red',bold=True))
        # sns.histplot(df[col], kde=True, bins=len(df[col].unique()))
        # plt.xticks(rotation=45)  # x축 라벨을 45도 기울입니다
        # plt.show()
# 각 컬럼별 0 값 비율,갯수보기
def column_zero_find(data):
    import matplotlib.pyplot as plt
    dataCount = data.columns.shape[0]
    for i in range(dataCount):

        data.columns[i]
        count_zero = (data[data.columns[i]] == 0).sum()
        count_non_zero = (data[data.columns[i]] != 0).sum()
        sizes = [count_zero, count_non_zero]
        labels = [f'{count_zero}개\n0인 데이터', f'{count_non_zero}개\n0이 아닌 데이터']
        colors = ['#ff9999','#66b3ff']
        
        #파이차트 생성
        plt.figure(figsize=(3, 3))
        plt.title(f"{data.columns[i]}컬럼 0비율")
        plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140)
        plt.axis('equal')
        plt.show()
# 각 컬럼별 상관도 높은순으로 뽑기
def show_corr(data,count):
    import numpy as np
    data2 = data.select_dtypes(include=np.number).columns
    filtered_corr = data2.corr()
    for i in range(len(filtered_corr.columns)):
        abs_values = filtered_corr[filtered_corr.columns[i]].abs()

        top_values = abs_values.nlargest(count)
        print(f"{filtered_corr.columns[i]} 컬럼의 상관계수 탑 5\n\n",top_values[0:count],"\n")


    ## 농가별로 데이터 나누기 
def seperate_col_data(df,colname):
    # df  =out
    # colname ='시설아이디'
    uniq_of_col_data = df[colname].unique().tolist()
    print(yellow(f" {colname}에는 {len(uniq_of_col_data)} 종류의 데이터 가있습니다. "))
    seperated_data = {}
    for i in uniq_of_col_data:
        seperated_data[i] = df[df[colname]==i] 
    data_shapes=[seperated_data[i].shape for i in uniq_of_col_data]
    
    print(yellow(f" 기존의 data 를 "))
    for (i,j) in zip(list(seperated_data.keys()),data_shapes):
        print(yellow(f"  {i} : {j}"))
    else:print(yellow(f" 로 쪼갭니다"))
    
    # print(yellow(f"{}"))
    # return seperated_data
## 농사기간 계산
def calc_duration(df, datetime_col):
    from datetime import datetime
    if datetime_col in df.columns :
        if df[datetime_col].dtype=='O':
            test_dt_start= df[datetime_col].sort_values(ignore_index=True,ascending=True).tolist()[0]
            test_dt_end= df[datetime_col].sort_values(ignore_index=True,ascending=True).tolist()[-1]
            
            # datetime.fromtimestamp(test_dt)
            date_start = datetime.strptime(test_dt_start, '%Y-%m-%d %H:%M').date()
            date_end = datetime.strptime(test_dt_end, '%Y-%m-%d %H:%M').date()
            return (date_end- date_start).days
        elif df[datetime_col].dtype=='int64':
            test_dt_start= df[datetime_col].sort_values(ignore_index=True,ascending=True).tolist()[0]
            test_dt_end= df[datetime_col].sort_values(ignore_index=True,ascending=True).tolist()[-1]
            date_start = datetime.strptime(str(test_dt_start), '%Y%m%d')
            date_end = datetime.strptime(str(test_dt_end), '%Y%m%d')
            return (date_end- date_start).days
## 주차 계산 함수
def calculate_week(date, base_date, base_week):
        base_date_timestamp = pd.Timestamp(base_date)

        # 날짜 차이 계산
        delta_days = (date - base_date_timestamp).dt.days

        # 기준 주차에서 날짜 차이를 주 단위로 변환
        week = base_week + delta_days // 7
        return week



def overfitting_test(
    trainig_score= 0.94,
    validation_score = 0.88
    ):
    if trainig_score> validation_score:
        print(yellow(" 훈련이 검증보다 잘되니 과대 적합입니다."))
    else:
         print(yellow(" 검증이 훈련보다 잘되니 과소 적합입니다."))

def train_val_generator(
    TRANING_DIR = './Data/rps/',
    VALIDATION_DIR = "./Data/rps-test-set/",
    img_size = (150,150),
    class_mode_='categorical' # binary
    ):
    ## train validation generator 
    print("\n◎Augumented training generator -- update(2024.10.16) by pdg")
    from tensorflow.keras.preprocessing.image import ImageDataGenerator
    # TRANING_DIR = './Data/rps/'
    
    ## data augumentation 을 위한 IDG  생성 
    training_datagen = ImageDataGenerator(
        rescale =1./255,
        rotation_range =40,
        width_shift_range =0.2,
        height_shift_range =0.2,
        shear_range = 0.2,
        horizontal_flip = True,
        fill_mode = 'nearest'
    )
    ## train data 를 dict 에서 가져와서 class 분류 한 tg
    train_generator = training_datagen.flow_from_directory(
        TRANING_DIR,
        target_size = img_size,
        class_mode = class_mode_
    )
    
    # VALIDATION_DIR = "./Data/rps-test-set/"
    validation_datagen = ImageDataGenerator(rescale = 1./255)
    validation_generator = validation_datagen.flow_from_directory(
        VALIDATION_DIR,
        target_size=img_size,
        class_mode=class_mode_
    )   
    
    return train_generator,validation_generator

def zip_extarction(source_path,target_folder_path):
    import zipfile
    zip_ref = zipfile.ZipFile(source_path,'r')
    zip_ref.extractall(target_folder_path)
    zip_ref.close()
    
def evaluate_model(model,test_data,test_label):
    classifications = model.predict(test_data)

    for i in range(len(test_data)):
        if i<10:
            print(f"{i+1}번째이미지는 {max(classifications[i])*100:.2f}%확률로 {test_label[i]}입니다.")
## Call back 을 이용해서 에포크 수를 자동으로 맞춰주자. 
def callback_setting(percent = 0.95):
    import tensorflow as tf
    class myCallback(tf.keras.callbacks.Callback): ## callback함수 를 상속함. 
        def on_epoch_end(self,epoch, logs={}):
            if logs.get('accuracy') is not None and logs.get('accuracy') > percent:
                print(f"\n 정확도 {percent*100}% 에 도달하여 훈련을 멈춥니다.!!")
                self.model.stop_training = True
    return myCallback()

def Analysis_title(Title):
    random_imoticon = ["🙀","👻","😜","🤗","🙄","🤑","🤖"]
    import numpy as np
    import random
    imo = random_imoticon[random.randrange(1,len(random_imoticon))]
    print(rainbow_green(f"✻✻✻✻______{imo*1} {Title} {imo*1}______✻✻✻✻",True))

def data_column_info(data_column_info_str = ""):
    if data_column_info_str:
        data_column_info = data_column_info_str
    else : 
        data_column_info=\
    '''
    - Molecule ChEMBL ID: ChEMBL 데이터베이스에서 분자의 고유 식별자     
    '''        
    lines = data_column_info.strip().split('\n')
    for line in lines:
        parts = line.split(':', 1)  # 콜론 기준으로 분리
        if len(parts) == 2:
            left_part = parts[0].strip()
            right_part = parts[1].strip()
            print(rainbow_orange(f"{left_part}:",True), rainbow_cyan(f"{right_part}"))
        else:
            print(line) 

def data_watch_one(start_, dataInfo=False, data_folder_path="./Data"):
    ## Data Fetching range
    start_data  =start_
    end_data =start_data+1
    
    Analysis_title(f"{start_data}-{end_data} 번 파일 데이터 보고 분석 ")
    data_dict= data_fetch(data_folder_path,start_data,end_data)
    
    ## data watching
    for i in range(len(data_dict.keys())):
        data_num= sorted(data_dict.keys())[i]
        print(yellow(f"{data_num} 파일 df.tail(3) "))
        # 화면 가운데 정렬하여 출력
        df_display_centered( key_selector(data_dict, i).tail(3))
        
        if dataInfo:
            plotSetting()
            step_3_0_dataInfo2( key_selector(data_dict,i))
    return data_dict

def data_watch_range(start_,end_, dataInfo = False,data_folder_path="./Data"):
    import pandas as pd
    from IPython.display import display, HTML

    ## Data Fetching
    data_folder_path=data_folder_path
    start_data  =start_
    end_data =end_+1
    Analysis_title(f"{start_data}-{end_data} 번 파일 데이터 보고 분석")
    data_dict= data_fetch(data_folder_path,start_data,end_data)
    if dataInfo:
        for i in range(len(data_dict.keys())):
            
            df =  key_selector(data_dict, i)
            data_num= sorted(data_dict.keys())[i]
            print(green("◎  "+f"{data_num}"+"--"*(100-(len(data_num)//2)) ,True))
            print(green(f"-Data info : ",True))
            df.info()
            # 화면 가운데 정렬하여 출력
            print(yellow(f"-DataFrame.head : ",True))
            display(df.head(3))
            print(yellow(f"-DataFrame.tail : ",True))
            display(df.tail(3))
            print(yellow("-Random sample Watching(7) : ",True))
            display(df.sample(7))
            
            print(r_orange(f"-DataFrame Describtion:",True))
            display(df.describe())
            
            plotSetting(pltStyle='default')
            step_3_0_dataInfo2( key_selector(data_dict,i))
            print(blue("--"*100))
        
    return data_dict

def drawing_graph_01(): 
    # 그래프 따라 그리기 
    import pandas as pd
    import matplotlib.pyplot as plt

    columns = ['년도', '시간제', '종일제', '기타', '이용가구계', '가구별월평균이용시간']

    # 데이터 추가
    
    data = [
        {'년도': 2019, '시간제': 66783, '종일제': 3702, '기타': 0, '이용가구계': 70485, '가구별월평균이용시간': 71.8},
        {'년도': 2020, '시간제': 56525, '종일제': 3138, '기타': 0, '이용가구계': 59663, '가구별월평균이용시간': 87.4},
        {'년도': 2021, '시간제': 57454, '종일제': 2617, '기타': 11718, '이용가구계': 71789, '가구별월평균이용시간': 87.9},
        {'년도': 2022, '시간제': 61138, '종일제': 2760, '기타': 14314, '이용가구계': 78212, '가구별월평균이용시간': 83.1},
        {'년도': 2023, '시간제': 66515, '종일제': 1890, '기타': 17695, '이용가구계': 86100, '가구별월평균이용시간': 85.6},
    ]

    df_test = pd.DataFrame(data, columns=columns)

    # 시각화
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # bar plot for 시간제, 종일제 (옆으로 나란히)
    width = 0.2  # 막대 너비 조절
    bars_시간제 =ax1.bar(df_test['년도'] - width/2, df_test['시간제'], width, label='시간제', color='skyblue')

    # 바 플롯 위에 데이터 값 표시 (텍스트로 붙이기)
    for i, bar in enumerate(bars_시간제):
        height = bar.get_height()
        x_pos = bar.get_x()
        bar_width = bar.get_width()
        ax1.text(x_pos + bar_width / 2, height, f'{height:.0f}', ha='center', va='bottom', fontsize=8,color='blue')
        
        
        
    bars_종일제 =ax1.bar(df_test['년도'] + width/2, df_test['종일제'], width, label='종일제', color='lightcoral')
    # 바 플롯 위에 데이터 값 표시 (텍스트로 붙이기)
    for i, bar in enumerate(bars_종일제):
        height = bar.get_height()
        x_pos = bar.get_x()
        bar_width = bar.get_width()
        ax1.text(x_pos + bar_width / 2, height, f'{height:.0f}', ha='center', va='bottom', fontsize=8)

    bars_기타 =ax1.bar(df_test['년도'] + width/2*3, df_test['기타'], width, label='기타', color='lightgreen')

    # 바 플롯 위에 데이터 값 표시 (텍스트로 붙이기)
    for i, bar in enumerate(bars_기타):
        height = bar.get_height()
        x_pos = bar.get_x()
        bar_width = bar.get_width()
        ax1.text(x_pos + bar_width / 2, height, f'{height:.0f}', ha='center', va='bottom', fontsize=8)

        
    ax1.plot(df_test['년도'], df_test['이용가구계']*1.05, label='이용가구계', marker='o', linestyle='-')
    # 선 그래프 점에 데이터 값 표시 (텍스트로 붙이기)


    for i, txt in enumerate(df_test['이용가구계']):
        ax1.text(df_test['년도'][i], txt + 5500, f'{txt:.0f}', ha='center', va='bottom', fontsize=8,color='black')
    ax1.set_xlabel('년도')
    ax1.set_ylabel('이용 가구 수')
    ax1.set_title('시간제, 종일제 이용 가구 수 변화 (2019-2023)')
    ax1.legend(loc='upper left')
    ax1.set_ylim([0,110000])
    # twin axes for line plot
    ax2 = ax1.twinx()
    ax2.plot(df_test['년도'], df_test['가구별월평균이용시간'], label='가구별 월평균 이용 시간', marker='o', linestyle='-', color='darkgreen')
    for i, txt in enumerate(df_test['가구별월평균이용시간']):
        ax2.text(df_test['년도'][i], txt + 1.5, f'{txt:.0f}', ha='center', va='bottom', fontsize=9, color='darkgreen')
    ax2.set_ylabel('가구별 월평균 이용 시간 (분)')  # y축 라벨 추가
    ax2.spines['right'].set_position(('outward', 0))  # 오른쪽 축 위치 조정
    ax2.tick_params(axis='y', labelcolor='darkgreen')  # y축 라벨 색상 변경
    ax2.legend(loc='upper right')
    ax2.set_ylim([60,150])
    plt.grid(True)
    plt.show()

def 시계열그래프_칼럼안에서특정데이터에해당하는_다른열들(df,group_col="",selected_row="",target_col = [''],기준연월_str = "기준연월"):
    import matplotlib.pyplot as plt, pandas as pd
    import platform
    from matplotlib import font_manager, rc
    # unicode 설정
    기준연월_str = "기준연월"
    target = df[df[group_col]==selected_row]
    print(yellow(f"Taget data : {selected_row}"))
    
    numeric_columns=target.select_dtypes(include=['number']).columns.tolist()
    print(yellow(f"numeric colums of taget data : {numeric_columns}"))
    
    target[기준연월_str] = pd.to_datetime(target[기준연월_str], format='%Y%m')

    df_display_centered(target.head(1))
    def visualize_01(target,numeric_columns,target_col):
        ### 특정 칼럼 시각화 ####
        plt.figure(figsize=(15,8))
        for column in numeric_columns:
            if column== 기준연월_str:
                continue
            # print(column)
            if column in target_col:
                plt.plot(target[기준연월_str],target[column],label=column, marker = 'o')
        # plt.plot(target['기준연월'],target[target_col],label=target_col, marker = 'o') 
        plt.title(f'{selected_row} - 시간에 따른 {target_col} 변화')
        plt.xlabel('기준연월')
        plt.ylabel(target_col)
        plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.xticks(rotation=45)
        plt.grid(True, linestyle='--', alpha=0.7)

        # x축 날짜 포맷 설정
        plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m'))
        plt.gca().xaxis.set_major_locator(plt.matplotlib.dates.MonthLocator(interval=3))
        plt.tight_layout()
        plt.show()
    visualize_01(target,numeric_columns,target_col)
    visualize_01(target,numeric_columns,['신규회원수','신규아동수','대기정회원수','웹회원수'])


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