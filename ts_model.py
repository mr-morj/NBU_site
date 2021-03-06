import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import warnings
import shap
from sklearn.metrics import mean_absolute_error
from statsmodels.tsa.stattools import adfuller
from sklearn.model_selection import train_test_split, TimeSeriesSplit
import time
import random
from sklearn.feature_selection import RFE, SelectFromModel
from sklearn.ensemble import RandomForestRegressor
from lightgbm import LGBMRegressor
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning) 
pd.set_option('mode.chained_assignment', None)

seed=47

def download_data_usd():
    data_usd = pd.read_excel('exchange_rate.xlsx')
    data_usd['date'] = pd.to_datetime(data_usd['date'],
                        format='%d.%m.%Y'
                                      )
    
    data_usd = data_usd.set_index('date')
    data_usd = data_usd['exrate']
    
    data_usd_curr = data_usd['2015-04-01':]
    return data_usd_curr

def download_data_economic():
    data = pd.read_excel('final_data.xlsx')
    data['date'] = pd.to_datetime(data['date'],
                        format='%d.%m.%Y'
                                      )
    
    data = data.set_index('date')
    data.drop(data.tail(1).index, inplace=True)
    
    return data

def predict_plot(X_train, X_valid, preds, y_true):
    
    st.markdown("Проілюструємо отримані значення на **графіку**.")
    fig, axs = plt.subplots(1, figsize=(6,4))
    fig.suptitle(f'Прогноз/реальні значення: {len(X_valid)} днів')

    axs.plot(data_usd_curr[X_valid.index[0]:X_valid.index[-1]].index, 
             data_usd_curr[X_valid.index[0]:X_valid.index[-1]].values, 
             'g-', label='Реальний курс')
    
    mae = mean_absolute_error(data_usd_curr[X_valid.index[0]:X_valid.index[-1]], preds)
    
    axs.plot(X_valid.index, preds, '-', label='Прогноз', color='royalblue')
    axs.fill_between(X_valid.index,
                preds-mae,
                preds+mae, color='k', alpha=.05, label='Похибка')
    axs.axhline(y=preds.mean(), linestyle='--',  color='b', label='Прознозоване середнє')
    axs.axhline(y=y_true.mean(), linestyle='--', color='g', label='Реальне середнє')
    fig.autofmt_xdate()
    axs.legend(loc=2)
    st.pyplot()

def create_shift(s, windows=[7,8,9,10]):
    
    cf = pd.DataFrame()

    for w in windows:    
        cf['shift_' + str(w)] = s.shift(w)
    
    for w in windows[1:]:
        cf['diff_shift_'+ str(w)] = -cf[f'shift_{windows[0]}'] + cf[f'shift_{w}']
    
    len_rost = 0
    len_spad = 0
    rost_spad = [0] * (windows[0]+1)
    
    check = cf[f'shift_{windows[0]}']
    for i in range(windows[0]+1, len(s)):
        if (s[i] > s[i-1]):
            
            len_rost = len_rost + 1
            len_spad = 0
            rost_spad.append(len_rost)
        elif (s[i] <= s[i-1]):
            
            len_spad = len_spad + 1
            len_rost = 0
            rost_spad.append(len_spad)

    cf['period_trend'] = rost_spad
    
    value = [0] * (windows[0]+1)
    for i in range(windows[0]+1, len(s)):
        value.append(s[i] - s[i-1])
    cf['day_increase'] = value
    
    return cf


def calc_roll_stats(s, windows=[3, 5, 7, 10]):

    roll_stats = pd.DataFrame()
    
    for w in windows:
        roll_stats['roll_mean_' + str(w)] = s.rolling(window=w, min_periods=1).mean()
        roll_stats['roll_std_' + str(w)] = s.rolling(window=w, min_periods=1).std()
        roll_stats['roll_min_' + str(w)] = s.rolling(window=w, min_periods=1).min()
        roll_stats['roll_max_' + str(w)] = s.rolling(window=w, min_periods=1).max()
        roll_stats['roll_q25_' + str(w)] = s.rolling(window=w, min_periods=1).quantile(0.25)
        roll_stats['roll_q75_' + str(w)] = s.rolling(window=w, min_periods=1).quantile(0.75)
             
    return roll_stats

def statictic_info(df, pr, windows=[30,50,60]):

    for w in windows:
        df['window_stationarity_' + str(w)] = [0]*len(df)
        n = int(len(df)/w) + 1
        for ci in range(n-1):
            P_result = adfuller(df[f'shift_{pr}'][ci*w:(ci+1)*w])
            df['window_stationarity_' + str(w)][ci*w:(ci+1)*w] = P_result[1]
    return df


def shap_plots(model, X, y_train):
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)
    plt.title('Оцінка важливості функій на основі SHAP')
    shap.summary_plot(shap_values,X,plot_type="bar",show=False)
    st.pyplot(bbox_inches='tight')
    plt.clf()
    
    st.markdown('Значення SHAP можуть також використовуватися для представлення розподілу навчального набору належного значення SHAP по відношенню до нашого прогнозу.')
    with st.spinner('Зображуємо ілюстрацію...'):
        plt.title('Загальний розподіл спостережень на основі SHAP')
        shap.summary_plot(shap_values,X,show=False)
        st.pyplot(bbox_inches='tight')
        plt.clf()
    
    st.markdown("Слід розуміти, **чому було зроблено конкретний прогноз** відновідно до наших вхідних даних.")
    expectation = explainer.expected_value
    individual = random.randint(min(range(len(X)))+1, max(range(len(X))))
    if individual>0:
        predicted_values = model.predict(X)
        real_value = y_train[individual]
        st.write('Справжній курс для обраного рядку: '+str(round(real_value,3))+' грн')
        st.write('Прогнозований курс для обраного рядку: '+str(round(predicted_values[individual],3))+' грн')
        st.write('Цей прогноз обчислюється так: середнє значення курсу ('+str(round(expectation,3))+' грн)'+' + сума значень SHAP.')
        st.write('Для цього індивідуального запису сума значень SHAP становить: '+str(round(sum(shap_values[individual,:]),3)))
        st.write('Це дає прогнозоване значення курсу: '+str(round(expectation,3))+' +\
                 '+str(round(sum(shap_values[individual,:]),3))+' = '+str(round(expectation+sum(shap_values[individual,:]),3))+' грн')
        st.markdown("Які функції повпливали на наш прогноз? **Червоні області збільшують прогноз, сині зменшують його.**")
        with st.spinner('Завантажуємо графіку...'):
            shap.force_plot(np.around(explainer.expected_value, decimals=2), np.around(shap_values[individual,:], decimals = 2), np.around(X.iloc[individual,:], decimals=2), matplotlib=True, show=False, text_rotation=20)
            st.pyplot(bbox_inches='tight',dpi=300,pad_inches=0)
            plt.clf()
        
        st.markdown("На графіку вище показані значення функцій. Значення SHAP представлені довжиною конкретної смуги. Однак, не зовсім зрозуміло, яке саме значення кожного SHAP _(це можна побачити нижче)_:")
        shap_table=pd.DataFrame(shap_values,columns=X.columns)
        st.table(shap_table.iloc[individual])


def true_select(s):
    
    color = 'limegreen' if s =='Відібрана' else 'tomato'
    return 'background-color: %s' % color
    
def feature_selection_forward(train_num, y, predict_size):
    
    if (predict_size<=7):
        lgbm=LGBMRegressor(n_estimators=900, learning_rate=0.05, num_leaves=32, colsample_bytree=0.2,
        reg_alpha=3, reg_lambda=1, min_split_gain=0.01, min_child_weight=40, random_state=seed)
    else:
        lgbm=LGBMRegressor(random_state=seed, n_estimators=100, learning_rate=0.025)
    
    st.markdown("На даному етапі проводиться відбір найкорисніших функцій для навчання. Всі результати автоматично занесуться до таблиці з відповідними значеннями.")
    check_df = pd.DataFrame({}, columns=['Функція', 'Результат'])
    with st.spinner('Проводимо відбір функцій...'):
        embeded_lr_selector = SelectFromModel(lgbm, threshold='median')
        embeded_lr_selector.fit(train_num, y)
        embeded_lr_support = embeded_lr_selector.get_support()
        train_clear = train_num.loc[:,embeded_lr_support].columns.tolist()
    l = random.sample(list(train_num.columns), len(train_num.columns))
    my_table = st.table(check_df)
    for i in l:
        t = 'Не відібрана'
        if i in train_clear:
            t = 'Відібрана'
        upd = pd.DataFrame({'Функція': [i], 'Результат': [t]})
        upd = upd.style.applymap(true_select, subset=['Результат'])
        my_table.add_rows(upd)
        time.sleep(0.3)
    return train_clear
        
data_usd_curr = download_data_usd()


def work_model(predict_size, select, sеlect_step, fs):
    
    #model = XGBRegressor(eval_metric='mae',
    #                         learning_rate=0.05,n_estimators=200,
    #                         max_depth=2,min_child_weight=3,
    #                         subsample=0.7,colsample_bytree=0.5, random_state=seed)      
    model = LGBMRegressor(random_state=seed, n_estimators=1000, learning_rate=0.025,
                           max_depth=7, num_leaves=10, min_child_weight=1)
    if (select =="Звичайне навчання"):
        data_usd = data_usd_curr.copy()     
        shift = create_shift(data_usd, [predict_size, predict_size+2, predict_size+4])
        roll_stats = calc_roll_stats(shift[f'shift_{predict_size}'], [predict_size, predict_size+2, predict_size+4, predict_size+6])

        X = pd.concat([shift, roll_stats], axis=1)
        y = data_usd.values
        X['y'] = y
        X = X.dropna()
        
        X = statictic_info(X, predict_size, [7, 14, 30])
        #X = X.dropna()
        
        if (predict_size<=7) or (predict_size>=20):
            X = X[-1200:]
        else:
            X = X[-1500:]
        y = X.y
        X = X.drop(labels=['y'], axis=1)
        X_train = X[:-predict_size]
        X_test = X[-predict_size:]
        y_train = y[:-predict_size]
        y_test = y[-predict_size:]
        if fs=="З відбором":
            train_clear = feature_selection_forward(X_train, y_train, predict_size)
            X_train = X_train[train_clear]
            X_test = X_test[train_clear]
        with st.spinner('Очікуйте результати...'):
            start = time.time()
            X_train_valid, X_test_valid, y_train_valid, y_test_valid = train_test_split(X_train, y_train, test_size=predict_size/len(X_train), random_state=seed, shuffle=False)
            
            model.fit(X_train, y_train, verbose=False)
            preds = model.predict(X_test)
            mae = mean_absolute_error(y_test, preds)
            finish = time.time()
        
    else:
        predict_lin = predict_size
        step = sеlect_step
        data_usd = data_usd_curr.copy()     

        shift = create_shift(data_usd, [step, step+2, step+4])
        roll_stats = calc_roll_stats(shift[f'shift_{step}'], [step, step+2, step+4, step+6])

        X = pd.concat([shift, roll_stats], axis=1)
        
        y = data_usd.values

        X['y'] = y
        X = X.dropna()
        X = statictic_info(X, step, [7, 14, 30])
        X = X[-1200:]
        
        y = X.y
        X = X.drop(labels=['y'], axis=1)

        X_train = X[:-predict_size]
        X_test = X[-predict_size:]
        y_train = y[:-predict_size]
        y_test = y[-predict_size:]
        if fs=="З відбором":
            train_clear = feature_selection_forward(X_train, y_train, predict_size)
            X_train = X_train[train_clear]
            X_test = X_test[train_clear]
        
        preds_full = []
        y_test_full = y_test.copy()
        y_train_full = y_train.copy()
        X_test_full = X_test.copy()
        X_train_full = X_train.copy()
        
        with st.spinner('Очікуйте результати...'):
            
            numb_steps = 0
            while (predict_size>=step):
                predict_size = predict_size - step
                numb_steps = numb_steps + 1
                
            last_step_size = predict_size
            start = time.time()
            for stt in range(1, numb_steps+1): 
                
                model.fit(X_train, y_train, verbose=False)
    
                preds = model.predict(X_test[:step])
                mae = mean_absolute_error(y_test[:step], preds)
                
                X_train = X_train.append(X_test[:step])
                
                pred_series = pd.Series(list(preds), index=[X_test[:step].index])
                y_train = np.append(y_train, pred_series)
                preds_full = preds_full+ preds.tolist()
                
                X_test = X_test.iloc[step:]
                y_test = y_test[step:]
                
                X_train['y'] = y_train
                X_test['y'] = y_test
                X_reinf = pd.concat([X_train, X_test], axis=0)
                
                data_usd_reinf = X_reinf.y
                X_reinf = X_reinf.drop(labels=['y'], axis=1)
    
                shift = create_shift(data_usd_reinf, [step, step+2, step+4])
                shift = shift.astype(float)
                roll_stats = calc_roll_stats(shift[f'shift_{step}'], [step, step+2, step+4, step+6])
                
                X_lag_reinf = pd.concat([shift, roll_stats], axis=1)
                y_lag_reinf = data_usd_reinf.values
                
                X_train = X_lag_reinf.iloc[:len(X_train)]
                X_test = X_lag_reinf.iloc[len(X_train):]
                y_train = y_lag_reinf[:len(y_train)]
                y_test = y_lag_reinf[len(y_train):]
                
                
            if last_step_size>0:
                model.fit(X_train, y_train, verbose=False)
                preds = model.predict(X_test)
                pred_series = pd.Series(list(preds), index=[X_test.index])
                y_train = np.append(y_train, pred_series)
                preds_full = preds_full+ preds.tolist()
                mae = mean_absolute_error(y_test_full, y_train[-len(y_test_full):])
            X_test = X_test_full
            X_train_full = X_train
            y_test = y_test_full
            y_train = y_train_full
            preds = np.array(preds_full)
            finish = time.time()
    return y_test, y_train, preds, mae, X_test, X_train, model, finish - start
