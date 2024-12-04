## 2024.11.28 : grid search best model, Voting Classifier update
## 2024.11.28 : yd, gd -> gold reward mark upgrade
class ModelTest:
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
## 분류 모델 
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
def ModelTest_step_1_LogisticRegression(X_train,y_train,X_valid,y_valid):
    """
# NMAE: normalized mean absolute error: 
실제 값고 ㅏ예측 값 사이의 차이를 절대값으로 취한뒤 실제값으로 나누어 평균을 나타냄. 오차의 크기가 원래 값에 대해 상대적으로 얼마나 큰지를 나타낸 정규화된 지표
## model = ModelTest_step_1_LinearRegression(X_train,y_train,X_valid,y_valid)
    """
    import matplotlib.pyplot as plt
    from sklearn.linear_model import LogisticRegression 
    # metric 정의 
    model = LogisticRegression(max_iter =180)
    model.fit(X_train,y_train)
    y_pred = model.predict(X_valid)
    acc = ACC(y_valid, y_pred)
    score = NMAE(y_valid,y_pred)
    print(yellow(f"로지스틱 회귀 분류 모델 NMAE: {score}"))
    print(yellow(f"로지스틱 회귀 분류 모델 ACC: {100*acc:.2f}%"))
    # 12. 모델 검증 시각화 
    make_plot(y_valid, y_pred)
    return model


## KFold Test
def ModelTest_KFold_test(train_x, train_y, model_ =""):
    """
    # # K- FOLD 검증데이터 => 5개의 모델 반환
    ## models = ModelTest_KFold_test(train_x, train_y, model_ ="")
    """
    from sklearn.ensemble import RandomForestClassifier 
    from sklearn.model_selection import StratifiedKFold
    kfold = StratifiedKFold( n_splits= 5, shuffle = True, random_state =42)
    models = []

    i = 0 
    y(" - KFODL 검증 시작 ")
    for train_idx , valid_idx in kfold.split(train_x,train_y):
        X_train,X_valid = train_x.iloc[train_idx], train_x.iloc[valid_idx]
        y_train, y_valid = train_y.iloc[train_idx], train_y.iloc[valid_idx]
        if model_:
            model = model_
        else:   
            model = RandomForestClassifier(random_state=42)
        model.fit(X_train, y_train)
        models.append(model)
        predict = model.predict(X_valid)
        # print(models[i])
        i+=1
        make_plot(y_valid,predict)
    return models 

## KFold - HardVoting, SoftVoting predict
def ModelTestKF_Hard_SoftVote_predict(test_x,train_y,models, HardVote= False,SoftVote=False):
    """
    # #KFOLD models 를 받아 soft vote 방식으로 predict 결과 도출 
    ## submission['quality']=ModelTestKF_Hard_SoftVote_predict(test_x,train_y,models, HardVote= False,SoftVote=True)
    """
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
        return pred_soft




## Grid search rf socre, parma 
def ModelTest_RFC_GridSearch(train_x,train_y):
    """
    # #5. RandomForestClassifier 최적 하이퍼 파라미터 탐색 
    ## ModelTest_RFC_GridSearch(train_x,train_y)
    """
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
## Grid Search RF, GB, ET 조합
def ModelTest_GridSearch_BestModel(train_x,train_y):
    """ 
    # # Grid Search RF, GB, ET 조합
    ## ModelTest_GridSearch_BestModel(train_x,train_y)
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
##sklearn 을 이용한 hard voting 앙상 블 분류기 학습 
def ModelTest_VotingClassifier(best_models,train_x,train_y,voting_ ='hard'):
    """
    # #sklearn 을 이용한 hard voting 앙상 블 분류기 학습 
    ## vc_model_hard = ModelTest_VotingClassifier(best_models,train_x,train_y,voting_='hard')
    ## vc_model_soft = ModelTest_VotingClassifier(best_models,train_x,train_y,voting_='soft')
    """
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
    
    return model 


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

def linear_regressor_prdict(train_input, train_target, test_input, test_target):
    from statistics import LinearRegression
    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## Linear Regression model 비교
    lin_regressor = LinearRegression()
    multi_output_regressor_lin = MultiOutputRegressor(lin_regressor)
    multi_output_regressor_lin.fit(train_input, train_target)
    y_pred_lin = multi_output_regressor_lin.predict(test_input)
    mse = mean_squared_error(test_target, y_pred_lin)
    rmse = np.sqrt(mse)
    r2 = r2_score(test_target, y_pred_lin) 
    
    #### 교차검증 
    scores_cv = cross_val_score(multi_output_regressor_lin,train_input,train_target,scoring='neg_mean_squared_error',cv=10)
    rmse_cv = np.sqrt(-scores_cv)
    print(f"Linear regression model RMSE: {rmse:.2f}")
    print(f"Linear regression model R2 score: {r2:.2f}")
    print("\t ",f"LR cv score : {rmse_cv}")
    print("\t ",f"LR cv RMSE  average : {rmse_cv.mean():.2f}")
            # 모델 저장
    joblib.dump(multi_output_regressor_lin, "Linear_model")
    print(f'모델이 {"Linear_model"} 이름으로 저장됨')
    predictions = multi_output_regressor_lin.predict(test_input)
    ModelTest.real_pred_compare(predictions,test_target,test_input)

def knn_regressor_predict(train_input, train_target, test_input, test_target, multi_out=True):
    ### Description: multiioutput 일때와 single output 일 때 구분해서 학습하도록 함. 
    ### Date : 2024.08.29 
    
    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.metrics import mean_squared_error
    from xgboost import XGBRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    ## KNN regression model
    knn_regressor = KNeighborsRegressor(n_neighbors=3)

    if multi_out:
        ## Multi Output Setting
        multi_output_regressor_knn = MultiOutputRegressor(knn_regressor)
        multi_output_regressor_knn.fit(train_input, train_target)
        score = multi_output_regressor_knn.score(test_input, test_target)
        y_pred_knn = multi_output_regressor_knn.predict(test_input)
        mse = mean_squared_error(test_target, y_pred_knn)
        rmse = np.sqrt(mse)
        # R2 스코어 계산
        r2 = r2_score(test_target, y_pred_knn)
        print(yellow(f'KNN(k=3) regression model score: {score}'))
        print(yellow(f'KNN(k=3) regression model RMSE: {rmse:.2f}'))
        print(yellow(f'KNN regression R2 score: {r2:.2f}'))
        #### 교차검증 
        scores_cv = cross_val_score(multi_output_regressor_knn, train_input, train_target, scoring='neg_mean_squared_error', cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        print(r_orange(f" ◉ KNN Cross Validation score : {rmse_cv}"))
        print(r_orange(f" ◉ KNN Cross Validation RMSE average : {rmse_cv.mean():.2f}"))
        # 모델 저장
        joblib.dump(multi_output_regressor_knn, "KNN_model")
        print(f'모델이 {"KNN_model"} 이름으로 저장됨')
        predictions = multi_output_regressor_knn.predict(test_input)

    else:  # multi_out이 False일 경우
        knn_regressor.fit(train_input, train_target)  # KNeighborsRegressor를 학습
        score = knn_regressor.score(test_input, test_target)
        y_pred_knn = knn_regressor.predict(test_input)
        mse = mean_squared_error(test_target, y_pred_knn)
        rmse = np.sqrt(mse)
        # R2 스코어 계산
        r2 = r2_score(test_target, y_pred_knn)
        print(yellow(f' ◉ KNN(k=3) regression model score: {score:.2f}'))
        print(yellow(f' ◉ KNN(k=3) regression model RMSE: {rmse:.2f}'))
        print(yellow(f' ◉ KNN regression R2 score: {r2:.2f}'))
        #### 교차검증 
        scores_cv = cross_val_score(knn_regressor, train_input, train_target, scoring='neg_mean_squared_error', cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        print(r_orange(f" ◉ KNN Cross Validation RMSE : "))
        for order,i in enumerate(rmse_cv):
            if order ==0:
                print("    : ",end="")
            print(f" {i:.3f} ",end=", ")
        else: print()
        print(r_orange(f" ◉ KNN Cross Validation RMSE average : {rmse_cv.mean():.2f}"))
        # 모델 저장
        joblib.dump(knn_regressor, "KNN_model")
        print(f'모델이 {"KNN_model"} 이름으로 저장됨')
        predictions = knn_regressor.predict(test_input)

def xgboost_regressor_predict(train_input, train_target, test_input, test_target, multi_out=True):
    """
    XGBoost 회귀 모델을 학습하고 예측합니다. 

    Args:
        train_input (pd.DataFrame): 학습 데이터의 입력 특성
        train_target (pd.Series): 학습 데이터의 목표 값
        test_input (pd.DataFrame): 테스트 데이터의 입력 특성
        test_target (pd.Series): 테스트 데이터의 목표 값
        multi_out (bool, optional): 여러 출력 값을 예측할지 여부. 기본값은 True입니다.

    Returns:
        None: 결과를 출력하고 모델을 저장합니다.
    """

    import numpy as np
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import mean_squared_error
    from xgboost import XGBRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib

    # xg_reg = XGBRegressor(enable_categorical=True)
    xg_reg = XGBRegressor(enable_categorical=True, feature_names=train_input.columns[:-1]) # feature_names 설정
    # 데이터 타입 변환 (필요에 따라)
    for col in train_input.columns:
        if col == 'Smiles':  # SMILES 컬럼은 제외
            continue
        train_input[col] = train_input[col].astype(int)  # 모든 열을 int 타입으로 변환 (필요에 따라 다른 타입으로 변환)
        test_input[col] = test_input[col].astype(int)  # test_input도 마찬가지로 변환

    if multi_out:
        # 여러 출력 값 예측 설정
        multi_output_regressor_xg = MultiOutputRegressor(xg_reg)
        multi_output_regressor_xg.fit(train_input, train_target)

        score = multi_output_regressor_xg.score(test_input, test_target)
        y_pred_xg = multi_output_regressor_xg.predict(test_input)
        mse = mean_squared_error(test_target, y_pred_xg)
        rmse = np.sqrt(mse)
        # R2 스코어 계산
        r2 = r2_score(test_target, y_pred_xg)   
        print(yellow(f' ◉ XGB regression model score: {score:.2f}'))
        print(yellow(f' ◉ XGBoost(3) regression model RMSE: {rmse:.2f}'))
        print(yellow(f' ◉ XGBoost regression model R2 score: {r2:.2f}'))
        ### 교차검증
        scores_cv = cross_val_score(multi_output_regressor_xg, train_input, train_target, scoring='neg_mean_squared_error', cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # 모델 저장
        joblib.dump(multi_output_regressor_xg, "XG_model")
        print(f'모델이 {"XG_model"} 이름으로 저장됨')
        print(r_orange(f" ◉ XGB Cross Validation RMSE : "))
        for order, i in enumerate(rmse_cv):
            if order == 0:
                print("    : ", end="")
            print(f" {i:.3f} ", end=", ")
        else:
            print()
        print(r_orange(f" ◉ XGB Cross Validation RMSE average : {rmse_cv.mean():.2f}"))
        predictions = multi_output_regressor_xg.predict(test_input)

    else:
        # 단일 출력 값 예측
        xg_reg.fit(train_input, train_target)

        score = xg_reg.score(test_input, test_target)
        y_pred_xg = xg_reg.predict(test_input)
        mse = mean_squared_error(test_target, y_pred_xg)
        rmse = np.sqrt(mse)
        # R2 스코어 계산
        r2 = r2_score(test_target, y_pred_xg)
        print(yellow(f' ◉ XGB regression model score: {score:.2f}'))
        print(yellow(f' ◉ XGBoost(3) regression model RMSE: {rmse:.2f}'))
        print(yellow(f' ◉ XGBoost regression model R2 score: {r2:.2f}'))
        ### 교차검증
        scores_cv = cross_val_score(xg_reg, train_input, train_target, scoring='neg_mean_squared_error', cv=10)
        rmse_cv = np.sqrt(-scores_cv)
        # 모델 저장
        joblib.dump(xg_reg, "XG_model")
        print(f'모델이 {"XG_model"} 이름으로 저장됨')
        print(r_orange(f" ◉ XGB Cross Validation RMSE : "))
        for order, i in enumerate(rmse_cv):
            if order == 0:
                print("    : ", end="")
            print(f" {i:.3f} ", end=", ")
        else:
            print()
        print(r_orange(f" ◉ XGB Cross Validation RMSE average : {rmse_cv.mean():.2f}"))
        predictions = xg_reg.predict(test_input)

    # ModelTest.real_pred_compare(predictions, test_target, test_input)

def randomforest_regressor_predict(train_input, train_target, test_input, test_target):
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.metrics import mean_squared_error
    from xgboost import XGBRegressor
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.model_selection import cross_val_score
    import joblib
    import os

    rf_reg = RandomForestRegressor(n_estimators=1, random_state=42)
    multi_output_regressor_rf = MultiOutputRegressor(rf_reg)
    multi_output_regressor_rf.fit(train_input, train_target)

    y_pred_rf = multi_output_regressor_rf.predict(test_input)
    mse = mean_squared_error(test_target, y_pred_rf)
    rmse = np.sqrt(mse)
    r2 = r2_score(test_target, y_pred_rf)

    print(yellow(f'RandomForest regression model RMSE: {rmse:.2f}'))
    print(f'RandomForest regression model R2 score: {r2:.2f}')

    # 교차 검증
    scores_cv = cross_val_score(multi_output_regressor_rf, train_input, train_target, 
                                scoring='neg_mean_squared_error', cv=10)
    rmse_cv = np.sqrt(-scores_cv)
    print("\t ", red(f"RF cv RMSE scores: {rmse_cv}"))
    print("\t ", green(f"RF cv RMSE average: {rmse_cv.mean():.2f}"))

    # R2 교차 검증
    r2_scores_cv = cross_val_score(multi_output_regressor_rf, train_input, train_target, 
                                scoring='r2', cv=10)
    print("\t ", red(f"RF cv R2 scores: {r2_scores_cv}"))
    print("\t ", green(f"RF cv R2 average: {r2_scores_cv.mean():.2f}"))

    # 모델 저장
    joblib.dump(multi_output_regressor_rf, "RF_model")
    print(f'모델이 {"RF_model"} 이름으로 저장됨')

    predictions = multi_output_regressor_rf.predict(test_input)
    ModelTest.real_pred_compare(predictions, test_target, test_input)


# SingleOutput regression model ( 데이콘 학습용)

def ModelTest_step_1_LinearRegression(X_train,y_train,X_valid,y_valid):
    """
# NMAE: normalized mean absolute error: 
실제 값고 ㅏ예측 값 사이의 차이를 절대값으로 취한뒤 실제값으로 나누어 평균을 나타냄. 오차의 크기가 원래 값에 대해 상대적으로 얼마나 큰지를 나타낸 정규화된 지표
## model = ModelTest_step_1_LinearRegression(X_train,y_train,X_valid,y_valid)
    """
    from sklearn.linear_model import LinearRegression 
    # metric 정의 
    import numpy as np 
    def NMAE(true,pred):
        score = np.mean(np.abs(true-pred) / true)
        return score
    model = LinearRegression()
    model.fit(X_train,y_train)
    y_pred = model.predict(X_valid)
    score = NMAE(y_valid,y_pred)
    print(f"Linear Regression(선형회귀모델) NMAE: {score}")
    return model


    

## TEXT Functions 
def df_display_centered(df, message=""):
    from IPython.display import display, HTML
    import pandas as pd 
    if message=="":
        message =f"   - DataFrame shape : {df.shape}"
    if type(df) != type(pd.DataFrame()):
        df=pd.DataFrame(df)
    print(green(message))
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

def yd(order,exp , df ,heading=3):
    import pandas as pd 
    if type(df) !=type(pd.DataFrame()):
        df = pd.DataFrame(df)
    from IPython.display import display
    y(f"{order}. {exp} "); 
    if heading ==0:
        g(f"   Displayed rows= {len(df)}/{len(df)}")
        # if int(df.isna().sum()) !=0:
        #     g(f"   Null included rows: {df.isnull().sum()}")
        df_display_centered(df)
    else:
        g(f"   Displayed rows= {heading}/{len(df)}")
        # if int(df.isna().sum()) !=0:
        #     g(f"   Null included rows: {df.isnull().sum()}")
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