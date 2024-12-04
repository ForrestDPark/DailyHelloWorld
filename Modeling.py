
# 12.2 :...something, Ridge update, kfold update
#12.1 : class process time, system update
## 2024.11.30 : regresision xgb rf update,..
## 2024.11.29 : yd, dfdisplay updatae
## 2024.11.28 : ModelTEst -> Modeling , numbering
## 2024.11.28 : grid search best model, Voting Classifier update
## 2024.11.28 : yd, gd -> gold reward mark upgrade
class Modeling:
    # 예시 데이터 (training_table과 target_table이 이미 존재한다고 가정)
    # training_table = pd.DataFrame(...)
    # target_table = pd.DataFrame(...)
    
    def __str__(self):
        return yellow(f"""
    ** 순서를 따라서 모델테스트를 해보세요! **
    
    1. 분류모델일 경우 (예시)
        - RF test : 
            submission = ModelTest.RandomForestClassifierModel(train_x,train_y, test_x,submission,target_col='target')
        - 저장     :s
            ubmission.to_csv("./심장질환예측/submission_rf.csv",index=False)
        - XGB test : 
            submission = ModelTest.XGBoostClassifierModel(train_x,train_y, test_x,submission,target_col='target')
        - 저장     :
            submission.to_csv("./심장질환예측/submission_xgb.csv",index=False)
    2. 회귀모델일 경우
    
    2.1 Single OUtput 회귀 
        
    
    """)
#################### [CLASSIFICATION MODEL] ##############################
#0. scoring , plot function
def NMAE(true,pred):
    import numpy as np
    score = np.mean(np.abs(true-pred) / true)
    return score
def ACC(y_true,pred):
    import numpy as np
    score = np.mean(y_true == pred)
    return score
def make_plot(y_true, pred):
    import pandas as pd, numpy as np, matplotlib.pyplot as plt
    # print(yellow(" - 모델 검증 시각화"))
    acc = ACC(y_true,pred)
    df_validation = pd.DataFrame({"y_true":y_true, 'y_pred':pred})
    # 검증 데이터 정답지 y_true 빈도수 (sorted)
    df_validation_count = pd.DataFrame(df_validation['y_true'].value_counts().sort_index())
    # 검증 데이터 예측지 y_pred 빈도수 (sorted)
    df_pred_count  = pd.DataFrame(df_validation['y_pred'].value_counts().sort_index())
    
    # pd.concat - 검증 데이터 정답지, 예측지 빈도수 합치기 
    df_val_pred_count = pd.concat([df_validation_count, df_pred_count],axis  =1).fillna(0)
    ###################################
    # 그래프 그리기
    ###################################
    x  = df_validation_count.index
    y_true_count = df_val_pred_count['y_true']
    y_pred_count = df_val_pred_count['y_pred']
    
    width = 0.35
    plt.figure(figsize=(8,3), dpi =150)
    plt.title("ACC : "+ str(acc)[:6])
    plt.xlabel('target')
    plt.ylabel('count')
    
    p1 = plt.bar([idx-width/2 for idx in x] , y_true_count , width , label= 'real')
    p2 = plt.bar([idx+width/2 for idx in x] , y_pred_count, width, label ='pred')
    plt.legend()
    plt.show()
#1. 기본적인 LogisticRegression 분류 model 을 검증 데이터를 통해 만듬. 
def Modeling_1_LogisticRegression(train_x,train_y,test_x):
    """
    # #기본적인 LogisticRegression 분류 model 을 검증 데이터를 통해 만듬. 
    ## lrc_model, lr_pred = Modeling_1_LogisticRegression(X_train,y_train,X_valid,y_valid)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling_1_LogisticRegression ======================="))
    import matplotlib.pyplot as plt
    from sklearn.linear_model import LogisticRegression 
    from sklearn.model_selection import train_test_split
    X_train,X_valid,y_train,y_valid = train_test_split(train_x,train_y, test_size=0.3,random_state=42)
    # metric 정의 
    
    
    
    model = LogisticRegression(max_iter =180)
    model.fit(X_train,y_train)
    y_pred = model.predict(X_valid)
    acc = ACC(y_valid, y_pred)
    score = NMAE(y_valid,y_pred)
    # NMAE: normalized mean absolute error: 
    #실제 값과예측 값 사이의 차이를 절대값으로 취한뒤 실제값으로 나누어 평균을 나타냄. 오차의 크기가 원래 값에 대해 상대적으로 얼마나 큰지를 나타낸 정규화된 지표
    
    y_(f" -로지스틱 회귀 분류 모델 NMAE: {score}")
    y_(f" -로지스틱 회귀 분류 모델 ACC: {100*acc:.2f}%")
    
    
    y_(" - kfold 모델 파라미터 튜닝 ")
    lr_model_dict = {
        'model_iblinear' : LogisticRegression(max_iter=180,solver='liblinear'),
        'model_lbfgs' : LogisticRegression(max_iter=180,solver='lbfgs'),
        'model_newton_cg' : LogisticRegression(max_iter=180,solver='newton-cg'),
        'model_newton_cholesky' : LogisticRegression(max_iter=180,solver='newton-cholesky'),
        'model_sag' : LogisticRegression(max_iter=180,solver='sag'),
        'model_saga': LogisticRegression(max_iter=180,solver='saga')
    }
    import numpy as np
    from sklearn.model_selection import KFold,cross_val_score
    kf = KFold(n_splits= 5, shuffle=True, random_state =42)
    # C cadidates
    c_list = [10e-7, 10e-6, 10e-5, 10e-4,10e-3,10e-2, 10e-3,1, 10,10^2]
    scores_list =[]
    model_score_list = []
    model_list=[]
    for model in lr_model_dict.keys():
        for c_val in c_list:
            lr_model_dict[model].C= c_val
            scores = cross_val_score(lr_model_dict[model],X_train,y_train, scoring = 'accuracy', cv=kf)
            scores_list.append(np.mean(scores))
        print(yellow(f" - {model} performance : {str(scores_list)}"))
        best_score = max(scores_list)
        model_score_list.append(best_score)
        model_list.append(model)
        optimal_C = c_list(np.argmax(scores_list))
        y(f" - Opimal C : {optimal_C}")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10,6))
        plt.plot(c_list, scores_list, marker= 'o', linestyle= '--')
        plt.xlabel(" C")
        plt.ylabel(" Cross-Validation Score(Accuracu)")
        plt.title(f" C vs. Accuracy Score of {model}")
        plt.xscale('log')
        plt.show()
    best_model = model_list[np.argmax(model_score_list)]
    best_model_score = np.max(model_score_list)
    final_model = lr_model_dict[best_model]
        
    # 12. 모델 검증 시각화 
    final_model.fit(train_x,train_y)
    lrc_prd =final_model.predict(test_x)
    
    make_plot(y_valid, lrc_prd)
    record_processing_time(end=True, started_time= start_time)
    return model, lrc_prd

#2. 모델(기본=RF)을 검증데이터 없이 KFold Test로 학습하여 평가된 모델들을 만듦
def Modeling_2_KFold_test(train_x, train_y, model_ =""):
    """
    # #모델(기본=RF)을 검증데이터 없이 KFold Test로 학습하여 평가된 모델들(5개)을 만듦
    ## KF_models = Modeling_2_KFold_test(train_x, train_y, model_ ="")
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling_2_KFold_test ======================="))
    from sklearn.ensemble import RandomForestClassifier 
    from sklearn.model_selection import StratifiedKFold
    kfold = StratifiedKFold( n_splits= 5, shuffle = True, random_state =42)
    models = []

    i = 0 
    if model_:
        model = model_
    else:   
        model = RandomForestClassifier(random_state=42)
        
    y(f" - KFODL 검증 시작 MODEL : {str(model)}")
    for train_idx , valid_idx in kfold.split(train_x,train_y):
        X_train,X_valid = train_x.iloc[train_idx], train_x.iloc[valid_idx]
        y_train, y_valid = train_y.iloc[train_idx], train_y.iloc[valid_idx]
        model.fit(X_train, y_train)
        models.append(model)
        predict = model.predict(X_valid)
        # print(models[i])
        i+=1
        make_plot(y_valid,predict)
    record_processing_time(end=True, started_time= start_time)

    return models 

#3. 모델들을 가지고 KFold - HardVoting, SoftVoting predict
def Modeling_3_KF_Hard_SoftVote_predict(test_x,train_y,models, HardVote= False,SoftVote=False):
    """
    # #모델들을 가지고 KFold - HardVoting, SoftVoting predict
    ## submission[target] = Modeling_3_KF_Hard_SoftVote_predict(test_x,train_y,KF_models, HardVote= False,SoftVote=True)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling_3_KF_Hard_SoftVote_predict ======================="))
    
    import pandas as pd, numpy as np
    if HardVote:
        pred_dict = {}
        for order,model in enumerate(models):
            pred_dict[f"pred_{order}"] = model.predict(test_x)

        pred_hard_vote = pd.DataFrame(pred_dict)
        # display(pred)
        y(" - 예측 최빈값 (Hard Voting) 정수형으로 예측값 변환")
        return pred_hard_vote.mode(axis=1).astype(int)
    if SoftVote:
        y(" - SOFT VOTE by pred_proba")
        
        pred_prob_dict ={}
        for order,model in enumerate(models):
            pred_prob_dict[f"pred_{order}"] = model.predict_proba(test_x)

        y(" - 각 분류기의 클래스 값 결정 확룰 을 모두 더한후 평균을 구하여 가장 높은 확률을 가지는 클래스 가 최종 보팅 ")
        
        for order, i in enumerate(pred_prob_dict.keys()):
            if order ==0:
                sum_df= pd.DataFrame(pred_prob_dict[i])
            else:
                sum_df+=pd.DataFrame(pred_prob_dict[i])
        
        y(" - train_y 의 class 확인")
        pred_soft_df=pd.DataFrame(sum_df/len(pred_prob_dict.keys()))
        print(train_y.value_counts().sort_index()) 
        
        y(" - pred_soft 의 class 확인")
        pred_soft = pd.DataFrame(np.array(pred_soft_df).argmax(axis=1))
        
        print(pred_soft.value_counts().sort_index())
        train_class_0 =train_y.value_counts().sort_index().index.tolist()[0]
        pred_soft_class_0= pred_soft.value_counts().sort_index().index.tolist()[0][0]
        diff= train_class_0-pred_soft_class_0
        y(f" -  클래스 차이 계산값: {diff}")
        pred_soft+=diff
        y(" - 차이를 조정한후 최종 pred soft class")
        print(pred_soft.value_counts().sort_index())
        record_processing_time(end=True, started_time= start_time)
        return pred_soft

#4. train_x,train_y 에 대함 RFC 모델 최적화 를 위해 GSCV 로 최적 성능 값 출력
def Modeling_4_RFC_GridSearch(train_x,train_y):
    """
    # #train_x,train_y 에 대함 RFC 모델 최적화 를 위해 GSCV 로 최적 성능 값 출력
    ## Modeling_4_RFC_GridSearch(train_x,train_y)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling_4_RFC_GridSearch ======================="))
    
    from sklearn.model_selection import GridSearchCV
    from sklearn.ensemble import RandomForestClassifier 

    params = {"n_estimators": [100,150,200],
            'criterion': ['gini','entropy']}
    rf_total = GridSearchCV(RandomForestClassifier(random_state=42), param_grid=params, cv=2,return_train_score= True, verbose= 3)
    rf_total.fit(train_x,train_y)
    y(" - GridSearch best score, parameters check")
    total_score = rf_total.best_score_
    total_params =rf_total.best_params_
    print(" - 최적 성능 :",total_score)
    print(" - 최적 파라미터 :",total_params)
    record_processing_time(end=True, started_time= start_time)

#5.  Grid Search RF, GB, ET 조합 한 각각의 best_models 추출
def Modeling_5_GridSearch_BestModel(train_x,train_y):
    """ 
    # #Grid Search RF, GB, ET 조합 한 각각의 best_models 추출
    ## best_models = Modeling_5_GridSearch_BestModel(train_x,train_y)
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.ensemble import ExtraTreesClassifier
    from sklearn.model_selection import GridSearchCV

    models = []
    rfc = RandomForestClassifier(random_state=42)
    models.append(rfc)

    gbc = GradientBoostingClassifier(random_state=42)
    models.append(gbc)

    etc = ExtraTreesClassifier(random_state=42)
    models.append(etc)
    y(" - rfc,gbc,etc 에 대한 parameter 를 Grid Search 합니다.")
    # grid search parameters (fixed typos)
    params = []
    params_rfc = {'n_estimators': [100, 120, 140]}  
    params.append(params_rfc)
    params_gbc = {'learning_rate': [0.05, 0.1, 0.15],
                'n_estimators': [60, 100, 140]}
    params.append(params_gbc)
    params_etc = {'n_estimators': [50, 100, 150]}
    params.append(params_etc)

    best_models = {}
    for i, model in enumerate(models):  # 수정: mode -> model
        print(f"Training model {i+1}/{len(models)}...") # 진행 상황 표시
        grid_search = GridSearchCV(model, param_grid=params[i], cv=2, return_train_score=True, verbose=1) # GridSearchCV를 각 모델마다 생성
        grid_search.fit(train_x, train_y) 
        best_models[i] = grid_search.best_estimator_
    y(" - best model results ")
    for i in best_models.keys():
        print(yellow(i),green(best_models[i]))
    return best_models

#6. Voting Classifier(hard,soft) 최적화된 모델들로 구성한 앙상블 분류기 생성
def Modeling_6_VotingClassifier(best_models,train_x,train_y,test_x,voting_ ='hard'):
    """
    # #Voting Classifier(hard,soft) 최적화된 모델들로 구성한 앙상블 분류기 생성 
    ## vc_model_hard = Modeling_6_VotingClassifier(best_models,train_x,train_y,test_x,voting_ ='hard')
    ## vc_model_soft = Modeling_6_VotingClassifier(best_models,train_x,train_y,test_x,voting_='soft')
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling_6_VotingClassifier ======================="))
    from sklearn.ensemble import VotingClassifier
    y(f" - Voting Classifier {voting_} voting model( rfc,gbc,etc) 을 생성합니다.")
    estimators = [
        ('rfc', best_models[0]),
        ('gbc', best_models[1]),
        ('etc', best_models[2])
    ]
    if voting_=='hard':
        model = VotingClassifier(estimators= estimators , voting=voting_)
    if voting_ == 'soft':
        model = VotingClassifier(estimators= estimators , voting=voting_)
    model.fit(train_x,train_y)
    
    
    record_processing_time(end=True, started_time= start_time)
    return model ,model.predict(test_x)
#7. 기타
##  RF model 생성 -> model pred
def ModelTest_RandomForestClassifierModel(train_x,train_y, test_x,submission,target_col='target',binary_target =False):
    """ 
    # #RF model 생성 -> model pred
    ## final_model,submission= ModelTest_RandomForestClassifierModel(train_x,train_y, test_x,submission,target_col=target)
    """
    g(" - RandomForest Classification model check")
    import warnings ; warnings.filterwarnings('ignore')
    from sklearn.model_selection import train_test_split
    X_train , X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    test_model_rf = RandomForestClassifier(random_state=42)
    test_model_rf_hyper = RandomForestClassifier(n_estimators = 150, max_depth= 12, min_samples_split =2, random_state= 42 )
    # test_model_rf_hyper =test_model_rf
    test_model_rf.fit(X_train,y_train)
    test_model_rf_hyper.fit(X_train,y_train)
    test_model_rf_hyper_pred = test_model_rf_hyper.predict(X_valid)
    
    
    if len(train_y.value_counts().sort_index().index) ==2: ## 이진 분류 일때
        g("   *** 이진분류 랜덤 포래스트 모분류델 성능 지표")
        accuracy_RF = accuracy_score(y_valid,test_model_rf_hyper_pred)
        precision_RF =precision_score(y_valid,test_model_rf_hyper_pred)
        recall_RF = recall_score(y_valid,test_model_rf_hyper_pred)
        f1_RF = f1_score(y_valid,test_model_rf_hyper_pred)
        print(yellow("  Accuracy :"),accuracy_RF)
        print(yellow("  Precision :"),precision_RF)
        print(yellow("  Recall"),recall_RF)
        print(yellow("  F1-score :"),f1_RF)
    
    else: # multi class target
        
        g("   *** 멀티클래스 랜덤 포래스트 회귀모델 성능 지표")
        accuracy_RF = accuracy_score(y_valid,test_model_rf_hyper_pred)
        precision_RF =precision_score(y_valid,test_model_rf_hyper_pred,average='macro')
        recall_RF = recall_score(y_valid,test_model_rf_hyper_pred,average='macro')
        f1_RF = f1_score(y_valid,test_model_rf_hyper_pred,average='macro')
        print(yellow("  Accuracy :"),accuracy_RF)
        print(yellow("  Precision :"),precision_RF)
        print(yellow("  Recall"),recall_RF)
        print(yellow("  F1-score :"),f1_RF)
        
    final_model = test_model_rf_hyper
    final_model.fit(train_x,train_y)
    final_predict = final_model.predict(test_x)
    submission[target_col]= final_predict
    return final_model,submission 
##  XGB model 생성 -> model pred
def ModelTest_XGBoostClassifierModel(train_x,train_y,test_x,submission, target_col='target'):
    """ 
    # #RF model 생성 -> model pred
    ## final_model,submission[target] = ModelTest_XGBoostClassifierModel(train_x,train_y, test_x,submission,target_col=target)
    """
    g(" -  XGBoost Classification model check")
    from sklearn.model_selection import train_test_split
    X_train , X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    test_model_xgb = XGBClassifier(random_state=42)
    test_model_xgb.fit(X_train,y_train)
    test_model_xgb_pred= test_model_xgb.predict(X_valid)
    g("   *** XGBoost 모델 성능 지표")
    accuracy_RF = accuracy_score(y_valid,test_model_xgb_pred)
    precision_RF =precision_score(y_valid,test_model_xgb_pred)
    recall_RF = recall_score(y_valid,test_model_xgb_pred)
    f1_RF = f1_score(y_valid,test_model_xgb_pred)
    print(yellow("  Accuracy :"),accuracy_RF)
    print(yellow("  Precision :"),precision_RF)
    print(yellow("  Recall"),recall_RF)
    print(yellow("  F1-score :"),f1_RF)
    
    final_model = test_model_xgb
    final_model.fit(train_x,train_y)
    final_predict = final_model.predict(test_x)
    submission[target_col]= final_predict
    return final_model,final_predict 

##-------------------------[END]-----------------------------------------##

#################### [REGRESSION MODEL]##############################



##------------------------------------------------------------------##

# MultiOutput regression model (경진대회용)
def real_pred_compare(predictions,test_target,test_input):
    print(yellow("🔸🔸🔸🔸🔸🔸[[실제 예측값 확인]]🔸🔸🔸🔸🔸🔸"))
    for idx,(pred_result,real,test_in) in enumerate(zip(predictions,test_target.values,test_input.values)):
        if idx < 4:
            str_real = "\t"
            str_pred = "\t"
            str_input = "\t"
            for i in list(real):
                str_real = "\t".join("{:>8d}".format(int(val)) for val in real)
            for j in list(map(int,(pred_result))):
                str_pred = "\t".join("{:>8d}".format(int(val)) for val in pred_result)
            for k in list(test_in):
                str_input += str(k) + "\t"

            
            print(f"***** {idx} 번째 test 결과 ***** ")
            print("인풋 정보"+"---"*200)
            print(f"인풋칼럼","\t".join((list(test_input.columns))),sep = "\t\t")
            print(f"***인풋\t  {str_input}", sep='\t')
            print("아웃풋 정보"+"---"*200)
            print(f"  ","\t".join((list(test_target.columns))),sep = "\t\t")
            formatted_columns = "\t".join("{:>8s}".format(col) for col in list(test_target.columns))
            print(f"    \t{formatted_columns}")
            print(f"실제\t  {str_real}", sep='\t')
            print(f"예측\t  {str_pred}", sep='\t')


# SingleOutput regression model (데이콘 학습용)

## 1: Modeling
def Modeling_1_Ridge_regression(train_x, train_y, test_x,mult_class =False, save =False,run_KF =True):
    """
    # # Linear regression model 
    ## lr_model , prediction= Modeling_1_Ridge_regression(train_x, train_y, test_x,mult_class =False, save =False,run_KF =True):
    """
    print(r_cy("\n======================= Modeling_1_Ridge_regression ======================="))
    start_time = record_processing_time(start=True)
    from sklearn.model_selection import train_test_split
    X_train, X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    
    from sklearn.linear_model import Ridge
    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    import joblib
    from sklearn.model_selection import KFold,cross_val_score

    ## Linear Regression model Validation and Score
    ridge = Ridge()
    multi_output_regressor_lin = MultiOutputRegressor(ridge)
    
    if mult_class:
        ## 검증학습 
        multi_output_regressor_lin.fit(X_train, y_train)
        y_pred_lin = multi_output_regressor_lin.predict(X_valid)
        final_model = multi_output_regressor_lin
    
    else:  ## single class
        if run_KF:
        #### 교차검증 
            kf = KFold(n_splits=5, shuffle=True, random_state=42)
            alpha_list = [i*0.001 for i in range(1,9)]
            scores_list = []
            for alpha in alpha_list:
                ridge = Ridge(alpha)
                scores = cross_val_score(ridge, X_train,y_train, scoring = 'neg_mean_squared_error',cv=kf)
                scores_list.append(np.mean(np.sqrt(-scores))) ## rmse
            # best alpha check 
            best_score = np.max(scores_list)
            print(f" - Best score of Ridge: {best_score}")
            optimal_alpha = alpha_list[np.argmax(scores_list)]
            print(f" - Optimal alpha:{optimal_alpha}")
            import matplotlib.pyplot as plt
            import warnings ; warnings.filterwarnings('ignore')
            # plotSetting(pltStyle="fivethirtyeight")
            plt.rcParams['font.family'] = 'Arial Unicode MS' # or another suitable font
            plt.figure(figsize=(10,6))
            plt.plot(alpha_list, scores_list, marker='o', linestyle= '--')
            plt.xlabel("Alpha")
            plt.ylabel(" Cross validation Score,( neg mean squared erro)")
            plt.title("alpha vs. CV score")
            plt.xscale('log')
            plt.show()
            # print("\t ",f"LR CROSS VAL score : {rmse_cv}")
            # y_(f" - CROSS VAL(5) RMSE 평균 : {rmse_cv.mean():.2f}")
        final_model= Ridge(alpha=optimal_alpha)
    
    ## 통합 학습
    final_model.fit(train_x, train_y)
    predictions = final_model.predict(test_x)
    mse = mean_squared_error(y_valid, y_pred_lin)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_valid, y_pred_lin) 
    y_(f" - 선형회귀 RMSE: {rmse:.2f}")
    y_(f" - 선형회귀 R2 score: {r2:.2f}")
    # 모델 저장
    if save :
        joblib.dump(multi_output_regressor_lin, "Linear_model")
        print(f'모델이 {"Linear_model"} 이름으로 저장됨')
    
    # real_pred_compare(predictions,test_target,test_input)
    ## 실제 값 비교 확인 
    # real_pred_compare(predictions,test_target,test_input)
    
    y(" - Validiation visualization ")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(8,4), dpi=150)
    plt.title(f"LinearRegression model RMSE:{rmse:.2f}")
    plt.plot(y_valid.reset_index(drop=True), alpha =0.6, label = 'real')
    plt.plot(y_pred_lin, alpha=0.6, label ='pred')
    plt.legend()
    plt.show()
    
    record_processing_time(end=True, started_time= start_time)
    return final_model, predictions

def Modeling_1_linear_regression(train_x, train_y, test_x,mult_class =False, save =False,run_KF =False):
    """
    # # Linear regression model 
    ## lr_model , prediction= Modeling_1_linear_regressor_predict(train_x, train_y, test_x,mult_class =False, save =False)
    """
    print(r_cy("\n======================= Modeling_1_linear_regressor_predict ======================="))
    start_time = record_processing_time(start=True)
    from sklearn.model_selection import train_test_split
    X_train, X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    
    from statistics import LinearRegression
    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## Linear Regression model Validation and Score
    lin_regressor = LinearRegression()
    multi_output_regressor_lin = MultiOutputRegressor(lin_regressor)
    
    if mult_class:
        ## 검증학습 
        multi_output_regressor_lin.fit(X_train, y_train)
        y_pred_lin = multi_output_regressor_lin.predict(X_valid)
        final_model = multi_output_regressor_lin
    
    else:  ## single class
        lin_regressor.fit(X_train,y_train)
        y_pred_lin = lin_regressor.predict(X_valid)
        final_model = lin_regressor
    
    ## 통합 학습
    final_model.fit(train_x, train_y)
    predictions = final_model.predict(test_x)
    
    
    mse = mean_squared_error(y_valid, y_pred_lin)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_valid, y_pred_lin) 
    y_(f" - 선형회귀 RMSE: {rmse:.2f}")
    y_(f" - 선형회귀 R2 score: {r2:.2f}")
    if run_KF:
        #### 교차검증 
        scores_cv = cross_val_score(final_model,train_x,train_y,scoring='neg_mean_squared_error',cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # print("\t ",f"LR CROSS VAL score : {rmse_cv}")
        y_(f" - CROSS VAL(10) RMSE 평균 : {rmse_cv.mean():.2f}")
    # 모델 저장
    if save :
        joblib.dump(multi_output_regressor_lin, "Linear_model")
        print(f'모델이 {"Linear_model"} 이름으로 저장됨')
    
    # real_pred_compare(predictions,test_target,test_input)
    ## 실제 값 비교 확인 
    # real_pred_compare(predictions,test_target,test_input)
    
    y(" - Validiation visualization ")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(8,4), dpi=150)
    plt.title(f"LinearRegression model RMSE:{rmse:.2f}")
    plt.plot(y_valid.reset_index(drop=True), alpha =0.6, label = 'real')
    plt.plot(y_pred_lin, alpha=0.6, label ='pred')
    plt.legend()
    plt.show()
    
    record_processing_time(end=True, started_time= start_time)
    return final_model, predictions

def Modeling_1_knn_regression(train_x, train_y, test_x,mult_class =False, save =False,run_KF =False):
    """
    # # KNN regression model 
    ## knn_model , prediction= Modeling_1_knn_regression(train_x, train_y, test_x,mult_class =False, save =False)
    """
    print(r_cy("\n======================= Modeling_1_knn_regression ======================="))
    start_time = record_processing_time(start=True)
    from sklearn.model_selection import train_test_split
    X_train, X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    
    from statistics import LinearRegression
    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## Linear Regression model Validation and Score
    knn_regressor = KNeighborsRegressor(n_neighbors=3)
    multi_output_regressor_lin = MultiOutputRegressor(knn_regressor)
    
    if mult_class:
        ## 검증학습 
        multi_output_regressor_lin.fit(X_train, y_train)
        y_pred_lin = multi_output_regressor_lin.predict(X_valid)
        final_model = multi_output_regressor_lin
    
    else:  ## single class
        knn_regressor.fit(X_train,y_train)
        y_pred_lin = knn_regressor.predict(X_valid)
        final_model = knn_regressor
    
    ## 통합 학습
    final_model.fit(train_x, train_y)
    predictions = final_model.predict(test_x)
    
    
    mse = mean_squared_error(y_valid, y_pred_lin)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_valid, y_pred_lin) 
    y_(f" - KNN회귀 RMSE: {rmse:.2f}")
    y_(f" - KNN회귀 R2 score: {r2:.2f}")
    if run_KF:
        #### 교차검증 
        scores_cv = cross_val_score(final_model,train_x,train_y,scoring='neg_mean_squared_error',cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # print("\t ",f"LR CROSS VAL score : {rmse_cv}")
        y_(f" - CROSS VAL(10) RMSE 평균 : {rmse_cv.mean():.2f}")
    # 모델 저장
    if save :
        joblib.dump(multi_output_regressor_lin, "Knn_model")
        print(f'모델이 {"Knn_model"} 이름으로 저장됨')
    
    # real_pred_compare(predictions,test_target,test_input)
    ## 실제 값 비교 확인 
    # real_pred_compare(predictions,test_target,test_input)
    
    y(" - Validiation visualization ")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(8,4), dpi=150)
    plt.title(f"KNN model RMSE:{rmse:.2f}")
    plt.plot(y_valid.reset_index(drop=True), alpha =0.6, label = 'real')
    plt.plot(y_pred_lin, alpha=0.6, label ='pred')
    plt.legend()
    plt.show()
    record_processing_time(end=True, started_time= start_time)
    return final_model, predictions

def Modeling_1_RandomForest_regression(train_x, train_y, test_x,mult_class =False, save =False, run_KF =False):
    """
    # #RandomForest regression model 
    ### - nestimators : number of decision trees(default =100)
    ### - criterion : splited tree quality measure => grow tree method(ex: squared_error)
    ### - max_depth, min_samples_split(노드분할을 위한 최소 샘플 데이터 수)
    ## rf_model , prediction= Modeling_1_RandomForest_regression(train_x, train_y, test_x,mult_class =False, save =False)
    """
    print(r_cy("\n======================= Modeling_1_RandomForest_regression ======================="))
    start_time = record_processing_time(start=True) 
    

    from sklearn.model_selection import train_test_split
    X_train, X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import mean_squared_error
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## RandomForestRegressor model Validation and Score
    rf_regressor = RandomForestRegressor(n_estimators=20, criterion= 'squared_error', random_state =42)
    multi_output_regressor_lin = MultiOutputRegressor(rf_regressor)
    best_RF_model,estimator, bestRF_prd = Modeling_2_GridSearch_reg_model(X_train, y_train,X_valid)
    
    if mult_class:
        ## 검증학습 
        multi_output_regressor_lin.fit(X_train, y_train)
        y_pred_rf = multi_output_regressor_lin.predict(X_valid)
        final_model = multi_output_regressor_lin
    
    else:  ## single class
        rf_regressor.fit(X_train,y_train)
        y_pred_rf = rf_regressor.predict(X_valid)
        final_model = rf_regressor
    
    ## 통합 학습
    final_model.fit(train_x, train_y)
    predictions = final_model.predict(test_x)
    
    ## Bestmodel 통합
    best_final= best_RF_model
    best_final.fit(train_x,train_y)
    best_predictions = best_final.predict(test_x)
    
    
    mse = mean_squared_error(y_valid, y_pred_rf)
    bmse =mean_squared_error(y_valid, bestRF_prd)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_valid, y_pred_rf) 
    br2 = r2_score(y_valid,bestRF_prd)
    y_(f" - 랜덤포레스트 RMSE: {rmse:.2f}")
    y_(f" - 랜덤포레스트 R2 score: {r2:.2f}\n")
    y_(f" - Best랜덤포레스트 RMSE: {bmse:.2f}")
    y_(f" - Best랜덤포레스트 R2 score: {br2:.2f}")
    if r2>br2: print("기본 랜덤포레스트 모델을 선택합니다.")
    else: print("BEST 랜덤포레스트 모델을 선택합니다.")
    final_model = final_model if rmse<bmse else best_final
    
    if run_KF:
        #### 교차검증 
        scores_cv = cross_val_score(final_model,train_x,train_y,scoring='neg_mean_squared_error',cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # print("\t ",f"LR CROSS VAL score : {rmse_cv}")
        y_(f" - CROSS VAL(10) RMSE 평균 : {rmse_cv.mean():.2f}")
    # 모델 저장
    if save :
        joblib.dump(multi_output_regressor_lin, "랜덤포레스트")
        print(f'모델이 {"랜덤포레스트"} 이름으로 저장됨')
    
    ## 실제 값 비교 확인 
    # real_pred_compare(predictions,test_target,test_input)
    
    y(" - Validiation  Result")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(12,4), dpi=150)
    plt.title(f"RandomForest model RMSE:{rmse:.2f}")
    plt.plot(y_valid.reset_index(drop=True), alpha =0.6, label = 'real')
    plt.plot(y_pred_rf, alpha=0.6, label ='pred')
    plt.plot(bestRF_prd, alpha=0.5, label = 'best')
    plt.legend()
    plt.show()
    # y(" - Feature importnace ")
    # import seaborn as sns, pandas as pd
    # feature_sereis = pd.Series(data = final_model.feature_importances_, index=train_x.columns)
    # feature_value_counts = feature_sereis.sort_values(ascending= False)
    # plt.figure(figsize=(12,4), dpi=150)
    # ax = sns.barplot(x= feature_value_counts, y= feature_value_counts.index,palette='viridis')
    # plt.xlabel("Importance")
    # plt.ylabel("Features")
    # plt.show()
    record_processing_time(end=True, started_time= start_time)

    
    return final_model, predictions

def Modeling_1_XGBoost_regresssion(train_x, train_y, test_x,mult_class =False, save =False, run_KF =False):
    """
    # #XGBoost regression model 
    ## xgb_model , prediction= Modeling_1_XGBoost_regresssion(train_x, train_y, test_x,mult_class =False, save =False)
    """
    print(r_cy("\n======================= Modeling_1_XGBoost_regresssion ======================="))
    start_time = record_processing_time(start=True) 

    from sklearn.model_selection import train_test_split
    X_train, X_valid , y_train, y_valid = train_test_split(train_x,train_y, test_size=0.3, random_state=42)
    
    import numpy as np
    from xgboost import XGBRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import mean_squared_error
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## XGBoost Regressor model Validation and Score
    ### - Boosting:  순차적으로 모델의 정확도를 높임. (이전 모델이 학습못한걸 반영해 다음모델을 만듬. )
    ### - object : 목적함수, n_es..: 트리수, eval_metric: 조기 종료 평가지표(rmse,mae,mape..), 
    ### - early_stopping_rounds: 조기종료조건, 평가지표향상 간으 반복회숫
    ### - 
    
    
    xgb_regressor = XGBRegressor(objective="reg:squarederror", n_estimators = 3000, eval_metric ='rmse',random_state =42)
    # xg_reg = XGBRegressor(enable_categorical=True, feature_names=train_input.columns[:-1]) # feature_names 설정
    
    if mult_class:
        ## 검증학습 
        multi_output_regressor_lin = MultiOutputRegressor(xgb_regressor)
        multi_output_regressor_lin.fit(X_train, y_train)
        multi_output_regressor_lin.fit(X_train,y_train, eval_set=[(X_valid,y_valid)], verbose=10)
        y_pred_rf = multi_output_regressor_lin.predict(X_valid)
        final_model = multi_output_regressor_lin
    
    else:  ## single class
        xgb_regressor.fit(X_train,y_train)
        # xgb_regressor.fit(X_train,y_train, eval_set=[(X_valid,y_valid)], verbose=10)
        xgb_regressor.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=0, early_stopping_rounds=10)
        y_pred_rf = xgb_regressor.predict(X_valid)
        final_model = xgb_regressor
    
    ## 통합 학습
    final_model.fit(train_x, train_y)
    predictions = final_model.predict(test_x)
    
    
    mse = mean_squared_error(y_valid, y_pred_rf)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_valid, y_pred_rf) 
    y_(f" - XGBoost RMSE: {rmse:.2f}")
    y_(f" - XGBoost R2 score: {r2:.2f}")
    
    if run_KF:
        #### 교차검증 
        scores_cv = cross_val_score(final_model,train_x,train_y,scoring='neg_mean_squared_error',cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # print("\t ",f"XGB CROSS VAL score : {rmse_cv}")
        y_(f" - CROSS VAL(10) RMSE 평균 : {rmse_cv.mean():.2f}")
    # 모델 저장
    if save :
        joblib.dump(multi_output_regressor_lin, "XGBOOST")
        print(f'모델이 {"XGBOOOST"} 이름으로 저장됨')
    
    ## 실제 값 비교 확인 
    # real_pred_compare(predictions,test_target,test_input)
    
    y(" - Validiation Result ")
    import matplotlib.pyplot as plt
    plt.figure(figsize=(12,4), dpi=150)
    plt.title(f"XGBoost model RMSE:{rmse:.2f}")
    plt.plot(y_valid.reset_index(drop=True), alpha =0.6, label = 'real')
    plt.plot(y_pred_rf, alpha=0.6, label ='pred')
    plt.legend()
    plt.show()
    
    y("- Feature importnace ")
    import seaborn as sns, pandas as pd
    feature_sereis = pd.Series(data = final_model.feature_importances_, index=train_x.columns)
    feature_value_counts = feature_sereis.sort_values(ascending= False)
    plt.figure(figsize=(12,4), dpi=150)
    ax = sns.barplot(x= feature_value_counts, y= feature_value_counts.index,palette='viridis')
    plt.xlabel("Importance")
    plt.ylabel("Features")
    plt.show()
    
    record_processing_time(end=True, started_time= start_time)

    
    return final_model, predictions


## 2 : GRID SEARCH
def Modeling_2_GridSearch_reg_model(train_x, train_y,test_x):
        """
        # #
        ## RF_model,estimator, RF_prd = Modeling_2_GridSearch_reg_model(train_x, train_y,test_x)
        """
        print(r_cy("\n======================= Modeling_2_GridSearch_reg_model ======================="))
        start_time = record_processing_time(start=True)
        
        from sklearn.model_selection import GridSearchCV
        from sklearn.ensemble import RandomForestRegressor 
        import pandas as pd
        params = { 'n_estimators': [100,150], 'max_depth': [5,10]}
        RF_model = GridSearchCV(RandomForestRegressor(),
                                param_grid=params,
                                cv =3 ,
                                scoring = 'neg_mean_absolute_error',
                                verbose =0
                                )
        
        RF_model.fit(train_x,train_y)
        RF_pred= RF_model.predict (test_x)
        scores_df = pd.DataFrame(RF_model.cv_results_)
        yd("[Grid Search] TOP3. hyperparameter, 검증평균점수, 검증점수 순위, 교차검증 폴드별 평균점수",
            scores_df[['params', 'mean_test_score', 'rank_test_score', 'split0_test_score', 'split1_test_score', 'split2_test_score']])

        y("최적의 점수 : {}".format(RF_model.best_score_))
        y("최적의 하이퍼 파라미터 : {}".format(RF_model.best_params_))
        estimator = RF_model.best_estimator_
        record_processing_time(end=True, started_time= start_time)
        return RF_model,estimator, RF_pred

## 7 : Regression type model start
def Modeling7_reg_model_start(train_x, train_y, test_x):
    """
    ## reg_pred_dict= Modeling7_reg_model_start(train_x, train_y, test_x)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling7_reg_model_start ======================="))
    # simple linear regression model
    lr_model , lr_prediction= Modeling_1_linear_regression(train_x, train_y, test_x,mult_class =False, save =False)

    # KNN regression model
    # knn_model , knn_prediction= Modeling_1_knn_regression(train_x, train_y, test_x,mult_class =False, save =False)

    # simple RandomForest regresiion model
    rf_model , rf_prediction= Modeling_1_RandomForest_regression(train_x, train_y, test_x,mult_class =False, save =False)

    #XGBoost regression model
    xgb_model , xgb_prediction= Modeling_1_XGBoost_regresssion(train_x, train_y, test_x,mult_class =False, save =False)
    reg_pred_dict ={
        "lr":lr_prediction,
        # "knn":knn_prediction,
        "rf":rf_prediction,
        "xgb":xgb_prediction
    }
    record_processing_time(end=True, started_time= start_time)
    return reg_pred_dict

## 7 : Classifier type model start
def Modeling7_clf_model_start(target_type,train_x, train_y, test_x):
    """
    clf_pred_dict =Modeling7_clf_model_start(target_type,train_x, train_y, test_x)
    """
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling7_clf_model_start ======================="))
    #기본적인 LogisticRegression 분류 model 을 검증 데이터를 통해 만듬.
    lrc_model,lrc_pred = Modeling_1_LogisticRegression(train_x, train_y, test_x)

    #모델(기본=RF)을 검증데이터 없이 KFold Test로 학습하여 평가된 모델들(5개)을 만듦
    KF_models = Modeling_2_KFold_test(train_x, train_y, model_ ="")
    
    #모델들을 가지고 KFold - HardVoting, SoftVoting predict
    rf_s_pred = Modeling_3_KF_Hard_SoftVote_predict(test_x,train_y,KF_models, HardVote= False,SoftVote=True)
    rf_h_pred = Modeling_3_KF_Hard_SoftVote_predict(test_x,train_y,KF_models, HardVote= True,SoftVote=False)

    #train_x,train_y 에 대함 RFC 모델 최적화 를 위해 GSCV 로 최적 성능 값 출력
    Modeling_4_RFC_GridSearch(train_x,train_y)
    
    #Grid Search RF, GB, ET 조합 한 각각의 best_models 추출
    best_models = Modeling_5_GridSearch_BestModel(train_x,train_y)
        
    #Voting Classifier(hard,soft) 최적화된 모델들로 구성한 앙상블 분류기 생성
    vc_h, vc_h_pred = Modeling_6_VotingClassifier(best_models,train_x,train_y,test_x,voting_='hard')
    vc_s,vc_s_pred = Modeling_6_VotingClassifier(best_models,train_x,train_y,test_x,voting_='soft')
    
    clf_pred_dict ={
        "lrc":lrc_pred,
        "vc_h":vc_h_pred,
        "vc_s":vc_s_pred,
        "rf_s":rf_s_pred,
        "rf_h":rf_h_pred
    }
    record_processing_time(end=True, started_time= start_time) 
    return clf_pred_dict

## 8 : Submission go!
def Modeling8_submission_go(target_type,submission,target,pred_dict,folder):
    start_time = record_processing_time(start=True)
    print(r_cy("\n======================= Modeling8_submission_go ======================="))
    if target_type=='Continuous':
        for i in pred_dict.keys():
            submission[target] = pred_dict[i]
            submission.to_csv(f"./{folder}/submission_{i}.csv", index=False)    
        y(" - 회귀 결과를 각 모델에 대하여 저장하였습니다")
    else:
        for i in pred_dict.keys():
            submission[target] = pred_dict[i]
            submission.to_csv(f"./{folder}/submission_{i}.csv", index=False)    
        y(" - 분류 결과를 각 모델에 대하여 저장하였습니다")
    record_processing_time(end=True, started_time= start_time)



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
    time.sleep(1) # 측정하고자 하는 코드 부분
    

## TEXT Functions 
def df_display_centered(df, message=""):
    from IPython.display import display, HTML
    import pandas as pd 
    if message=="":
        message =f" - SHAPE : {df.shape}"
    if type(df) != type(pd.DataFrame()):
        df=pd.DataFrame(df)
    # print(green(message))
    display(HTML('<div style="text-align: center; margin-left: 30px;">{}</div>'.format(df.to_html().replace('<table>', '<table style="margin: 0 auto;">'))))

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
        'r_orange': rainbow_colors[1],
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
        print(r_y('🥇'+string))
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
def r_orange(str, b=False):return colored_text(str, 'r_orange', bold=b)
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
    g(f"{order}. {exp} "); 
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
            # DataPreprocessing.plotSetting()
            # DataPreprocessing.dataInfo(input_data)
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