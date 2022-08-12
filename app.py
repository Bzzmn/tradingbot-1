import json, pandas as pd, numpy as np, pymongo, config
from ssl import ALERT_DESCRIPTION_USER_CANCELLED

from flask import Flask, request, jsonify, render_template
from binance import Client
from binance.enums import *
from binance.helpers import round_step_size
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
client_pm = pymongo.MongoClient(config.CONNECTION_STRING)
client_bi = Client(config.API_KEY, config.API_SECRET)
now = datetime.now()

def order_market_buy(symbol, contracts):
    try:
        print(f'sending order MARKET - BUY -  {symbol} {contracts}')
        order = client_bi.order_market_buy(symbol=symbol, quantity=contracts )
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order

def order_market_sell(symbol, contracts):
    try:
        print(f'sending order MARKET - SELL -  {symbol} {contracts}')
        order = client_bi.order_market_sell(symbol=symbol, quantity=contracts )
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order 

def transfer_s2m(asset, amount):
    try:
        print(f'sending transfer spot to margin {asset} - {amount}')
        order = client_bi.transfer_spot_to_margin(asset=asset, amount=amount)
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order

def transfer_m2s(asset, amount):
    try:
        print(f'sending transfer margin to spot {asset} - {amount}')
        order = client_bi.transfer_margin_to_spot(asset=asset, amount=amount)
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order

def get_loan(asset, amount):
    try:
        print(f'sending loan request {asset} - {amount}')
        order = client_bi.create_margin_loan(asset=asset, amount=amount)
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order

def repay_loan(asset, amount):
    try:
        print(f'sending loan repay {asset} - {amount}')
        order = client_bi.repay_margin_loan(asset=asset, amount=amount)
    except Exception as e:
        print('an exception occured - {}'.format(e))
        return False

    return order    

start_time = now.strftime("%Y/%m/%d, %H:%M:%S")
print("Current Time is :", start_time)

## INITIATE DB ##
db = client_pm['webapp-tdbt']

print ('======StartPoint=========')

#current_position = db['current_position']
#current_position.insert_one({"symbol":"BTCUSDT", "position":"flat", "max_investment%":0.1})
#current_position.insert_one({"symbol":"ADAUSDT", "position":"flat", "max_investment%":0.5})

## CONNEX ##
@app.route("/")
def welcome():
    return render_template('index.html')

@app.route("/webapp-tdbt", methods=['POST'])
def webhook():
    data = json.loads(request.data)
    if data['passfrase'] != config.WEBHOOK_PASSPHRASE:
        return {
            'code': 'error', 
            'message': 'something went wrong' 
        }
    data         
    symbol = data['ticker']

    print("start_time :", now.strftime("%Y/%m/%d, %H:%M:%S"))
    print('symbol: ',symbol)

    if (db['exchange_info']).find_one({"symbol":symbol}) == None:
        info=client_bi.get_symbol_info(symbol)
        if info:     
            db['exchange_info'].insert_one(info)
        else:
            print('Error: symbol doesnt exist in exange')
            return {
            'code': 'error', 
            'message': 'something went wrong'
            }
    
    if (db['current_position']).find_one({"symbol":symbol}) == None:
        print('Error: symbol doesnt exist in database')
        return {
            'code': 'error', 
            'message': 'something went wrong'
            }

    if (db['trade_count']).find_one({"symbol":symbol}) == None:        
        db['trade_count'].insert_one({"symbol":symbol, "position":"flat", "max_investment%":0.0})

    if data['strategy']['alert_message'] == 'Long Entry!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'long':
                print ('Error: posicion ya tomada')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'flat':
                print('caso 1: Long Entry')

                #---paso 1 - Long Entry               
                #---1.1 buy asset

                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                qty_pivot = (df.loc[df['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0,
                                    'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df1 = pd.DataFrame(client_bi.get_all_tickers())
                df2 = pd.merge(df, df1, on="symbol")
                df2['equity'] = df2['price'].astype(float) * df2['free'].astype(float)
                df2 = pd.concat([df2, df4])
                df2['equity'] =  df2['equity'].astype(float) 
                equity_spot = df2['equity'].sum()

                df3 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df3 = df3[((df3['borrowed']).astype(float) > 0) | ((df3['free']).astype(float) > 0)]
                df3['symbol'] = (df3['asset']+'USDT')
                qty_pivot = (df3.loc[df3['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 'borrowed':0, 'interest':0,
                                    'netAsset':qty_pivot, 'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df3 = pd.merge(df3, df1, on="symbol")
                df3['equity'] = df3['price'].astype(float) * df3['netAsset'].astype(float)
                df3 = pd.concat([df3, df4])
                df3['equity'] =  df3['equity'].astype(float) 
                equity_margin = df3['equity'].sum()

                equity = equity_margin + equity_spot

                if (equity * position['max_investment%']) > equity_spot:
                    amount = equity_spot
                else:
                    amount = equity * position['max_investment%']
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                for line in ex_info['filters']:
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))

                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))

                price = float(data['strategy']['order_price'])
                price = round_step_size(price, tickSize)
                contracts = float(amount)/price  
                contracts = round_step_size(contracts, stepSize)

                order = order_market_buy(symbol, contracts)
                order = order['fills']
                for line in order:
                    price = float(line.get('price'))
                    tranId = float(line.get('tradeId'))

                #---1.2 register
                
                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
               
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Long", 
                                    "Signal":"Buy", "DateTime": datetime.now() , 
                                    "Price":price, "Contracts":contracts})
                
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"long"}})

        elif position['position'] == 'short':
                print('caso 2: Short Exit + Long Entry')

                #---paso 1 - Short Exit 
                #---1.1 repay loan    
            
                df1 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df1 = df1[((df1['borrowed']).astype(float) > 0) | ((df1['free']).astype(float) > 0)]
                df1['symbol'] = (df1['asset']+'USDT')

                df_i = (df1.loc[df1['symbol']== symbol , :])
                amount = df_i.iloc[0]['borrowed']
                asset = df_i.iloc[0]['asset']

                order = repay_loan(asset ,amount)
                tranId = order['tranId']
                
                #---1.2 repay interest

                df_i = (df1.loc[df1['asset']== 'BNB' , :])
                rp_amount = df_i.iloc[0]['interest']
                if float(rp_amount) > 0:
                    order = repay_loan('BNB' ,rp_amount)

                #---1.3 register

                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                for line in ex_info['filters']:
                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))           
                
                price = float(data['strategy']['order_price'])
                price = round_step_size(price, tickSize)

                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Short", "Signal":"Buy", 
                                "DateTime": datetime.now(), "Price":price,
                                "Contracts":float(amount)})
            
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"flat"}})

                #---1.4 transfer margin to spot

                borrowed = (df1['borrowed'].astype(float)).sum()
                actual_debt = borrowed - float(amount)

                if actual_debt == 0:
                    df_i = (df1.loc[df1['asset']== 'USDT' , :])
                    amount = df_i.iloc[0]['free']
                    transfer_m2s ('USDT',amount) 

                else:    
                    amount = "{:.2f}".format(float(amount) * price )
                    transfer_m2s ('USDT',amount)     

                #---paso 2 - Long Entry            
                #---2.1 Buy asset  
                                
                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                qty_pivot = (df.loc[df['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0,
                                    'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df1 = pd.DataFrame(client_bi.get_all_tickers())
                df2 = pd.merge(df, df1, on="symbol")
                df2['equity'] = df2['price'].astype(float) * df2['free'].astype(float)
                df2 = pd.concat([df2, df4])
                df2['equity'] =  df2['equity'].astype(float) 
                equity_spot = df2['equity'].sum()

                df3 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df3 = df3[((df3['borrowed']).astype(float) > 0) | ((df3['free']).astype(float) > 0)]
                df3['symbol'] = (df3['asset']+'USDT')
                qty_pivot = (df3.loc[df3['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 'borrowed':0, 'interest':0,
                                    'netAsset':qty_pivot, 'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df3 = pd.merge(df3, df1, on="symbol")
                df3['equity'] = df3['price'].astype(float) * df3['netAsset'].astype(float)
                df3 = pd.concat([df3, df4])
                df3['equity'] =  df3['equity'].astype(float) 
                equity_margin = df3['equity'].sum()

                equity = equity_margin + equity_spot

                if (equity * position['max_investment%']) > equity_spot:
                    amount = equity_spot
                else:
                    amount = equity * position['max_investment%']
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                for line in ex_info['filters']:
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))

                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))

                price = float(data['strategy']['order_price'])
                price = round_step_size(price, tickSize)
                contracts = float(amount)/price  
                contracts = round_step_size(contracts, stepSize)

                order = order_market_buy(symbol, contracts)
                order = order['fills']
                for line in order:
                    price = float(line.get('price'))
                    tranId = float(line.get('tradeId'))

                #---2.2 register
                
                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
               
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Long", 
                                    "Signal":"Buy", "DateTime": datetime.now() , 
                                    "Price":price, "Contracts":contracts})
                
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"long"}})

    elif data['strategy']['alert_message'] == 'Short Entry!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'short':
                print ('Error: posicion ya tomada')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }
 
        elif position['position'] == 'flat':
                print('caso 3: Short Entry')

                #---paso 1 - Short Entry 
                #---1.1 transfer spot to margin

                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                qty_pivot = (df.loc[df['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 
                                'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df5 = pd.DataFrame(client_bi.get_all_tickers())   
                dfp = (df5.loc[df5['symbol'] == symbol, :]).astype(str) 
                price = dfp.iloc[0]['price']

                df1 = pd.merge(df, df5, on="symbol")
                df1['equity'] = df1['price'].astype(float) * df1['free'].astype(float)
                df1 = pd.concat([df1, df4])
                print(df1)
                equity_spot = (df1['equity'].astype(float)).sum()
                
                df3 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df3 = df3[((df3['borrowed']).astype(float) > 0) | ((df3['free']).astype(float) > 0)]
                df3['symbol'] = (df3['asset']+'USDT')
                qty_pivot = (df3.loc[df3['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 'borrowed':0, 'interest':0,
                                    'netAsset':qty_pivot, 'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df2 = pd.merge(df3, df5, on="symbol")
                df2['equity'] = df2['price'].astype(float) * df2['netAsset'].astype(float)
                df2 = pd.concat([df2, df4])
                df2['equity'] =  df2['equity'].astype(float) 
                equity_margin = df2['equity'].sum()
                
                equity = equity_margin + equity_spot   

                if (equity * position['max_investment%']) > equity_spot:
                    amount = "{:.2f}".format(equity_spot)
                else:
                    amount = "{:.2f}".format(equity * position['max_investment%'])

                transfer_s2m ('USDT',amount) 

                #---1.2 get loan 
                
                amount = "{:.2f}".format(float(amount))
                contracts = float(amount)/float(price)     
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol}) 
                loan_coin = ex_info['baseAsset']
                for line in ex_info['filters']:
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))
                
                contracts = str(round_step_size(contracts, stepSize))
               
                order = get_loan(loan_coin,contracts)
                tranId = order['tranId']

                #---1.3 register 

                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Short", "Signal":"Sell",
                                "DateTime": datetime.now(), 
                                "Price":float(price), "Contracts":float(contracts)})
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"short"}})
        
        elif position['position'] == 'long':
                print('caso 4: Long Exit + Short Entry')

                #---paso 1 - Long Exit
                #---1.1 sell asset  

                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                baseAsset = ex_info['baseAsset']
                
                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                
                qty_baseAsset = (df.loc[df['asset']== baseAsset , :])
                contracts = qty_baseAsset.iloc[0]['free'] 
               
                for line in ex_info['filters']:     
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))
                
                contracts = round_step_size(contracts, stepSize)
                
                order = order_market_sell(symbol, contracts)
                order = order['fills']
 
                for line in order:
                    price = float(line.get('price'))
                    tranId = float(line.get('tradeId'))

                #---1.2 register
                
                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
               
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Long", 
                                    "Signal":"Sell", "DateTime": datetime.now() , 
                                    "Price":price, "Contracts":contracts})
                
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"flat"}})

                #---paso 2 - Short Entry 
                #---2.1 transfer spot to margin

                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                qty_pivot = (df.loc[df['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 
                                'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df5 = pd.DataFrame(client_bi.get_all_tickers())   
                dfp = (df5.loc[df5['symbol'] == symbol, :]).astype(str) 
                price = dfp.iloc[0]['price']

                df1 = pd.merge(df, df5, on="symbol")
                df1['equity'] = df1['price'].astype(float) * df1['free'].astype(float)
                df1 = pd.concat([df1, df4])
                equity_spot = (df1['equity'].astype(float)).sum()
                
                df3 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df3 = df3[((df3['borrowed']).astype(float) > 0) | ((df3['free']).astype(float) > 0)]
                df3['symbol'] = (df3['asset']+'USDT')
                qty_pivot = (df3.loc[df3['asset']=='USDT' , 'free']).astype(float) 
                df4 = pd.DataFrame ({ 'asset':'USDT', 'free': qty_pivot , 'locked':0, 'borrowed':0, 'interest':0,
                                    'netAsset':qty_pivot, 'symbol':'USDTUSDT','price':1, 'equity': qty_pivot })

                df2 = pd.merge(df3, df5, on="symbol")
                df2['equity'] = df2['price'].astype(float) * df2['netAsset'].astype(float)
                df2 = pd.concat([df2, df4])
                df2['equity'] =  df2['equity'].astype(float) 
                equity_margin = df2['equity'].sum()
                
                equity = equity_margin + equity_spot           
                
                if (equity * position['max_investment%']) > equity_spot:
                    amount = "{:.2f}".format(equity_spot)
                else:
                    amount = "{:.2f}".format(equity * position['max_investment%'])

                transfer_s2m ('USDT',amount) 

                #---2.2 get loan 

                amount = "{:.2f}".format(float(amount))
                contracts = float(amount)/float(price) 
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol}) 
                loan_coin = ex_info['baseAsset']
                for line in ex_info['filters']:
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))
                
                contracts = str(round_step_size(contracts, stepSize))
               
                order = get_loan(loan_coin,contracts)
                tranId = order['tranId']

                #---2.3 register 

                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Short", "Signal":"Sell",
                                "DateTime": datetime.now(), 
                                "Price":float(price), "Contracts":float(contracts)})
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"short"}})  
                
    elif data['strategy']['alert_message'] == 'TP Long!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'short':
                print ('Error: posicion incorrecta para el take profit')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'flat':
                print ('Error: posicion incorrecta para el take profit')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'long':
                print('caso 5: Take profit long')

                #---paso 1 - Take profit
                #---1.1 sell asset
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                baseAsset = ex_info['baseAsset']
                
                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                
                qty_baseAsset = (df.loc[df['asset']== baseAsset , :])
                contracts = float(qty_baseAsset.iloc[0]['free'] )
                
                for line in ex_info['filters']:
                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))
                    
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))
                
                currentPrice = round_step_size((float(data['strategy']['order_price'])), tickSize)

                tradeCount = (db['trade_count']).find_one({'symbol': symbol})
                tradeCount = float(tradeCount['count'])

                ex_info=(db['registro_trx']).find_one({ '$and': [{"Trade#":tradeCount},{'symbol': symbol}]})
                initialPrice = ex_info['Price']

                p_contracts = contracts*((currentPrice - initialPrice)/initialPrice)
                p_contracts = round_step_size(p_contracts, stepSize)

                rem_contracts = contracts-p_contracts
                rem_contracts = round_step_size(rem_contracts, stepSize)

                sell_amount = p_contracts * currentPrice 
                
                if sell_amount < 10:
                    print ('Error: Monto TP menor a 10USDT minimo')       
                    return {
                        'code': 'error', 
                        'message': 'something went wrong' 
                        }
                order = order_market_sell(symbol, str(p_contracts))

                order = order['fills']
 
                for line in order:
                    price = float(line.get('price'))
                    tranId = float(line.get('tradeId'))

                #---1.2 register
                
                reg_trx = db['registro_trx'] 
                reg_trx.update_one({ '$and': [{"Trade#":tradeCount},{'symbol': symbol}]}, {'$set':{"Contracts":p_contracts}})

                initialDateTime = ex_info['DateTime']
                
                count = db['trade_count'].find_one({'symbol': symbol}) 
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Long", 
                                    "Signal":"TPl", "DateTime": datetime.now() , 
                                    "Price":price, "Contracts":p_contracts})

                count = db['trade_count'].find_one({'symbol': symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Long", 
                                    "Signal":"Buy", "DateTime": initialDateTime , 
                                    "Price":initialPrice, "Contracts":(rem_contracts)})
    
    elif data['strategy']['alert_message'] == 'TP Short!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'long':
                print ('Error: posicion incorrecta para el take profit')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'flat':
                print ('Error: posicion incorrecta para el take profit')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'short':
                print('caso 6: Take profit short')

                #---paso 1 - Take profit
                #---1.1 repay loan

                df1 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df1 = df1[((df1['borrowed']).astype(float) > 0) | ((df1['free']).astype(float) > 0)]
                df1['symbol'] = (df1['asset']+'USDT')

                dfx = (df1.loc[df1['symbol']== symbol , :])
                contracts = dfx.iloc[0]['borrowed']

                tradeCount = (db['trade_count']).find_one({'symbol':symbol})
                tradeCount = float(tradeCount['count'])

                ex_info=(db['registro_trx']).find_one({ '$and': [{"Trade#":tradeCount},{'symbol': symbol}]})
                initialPrice = ex_info['Price']
                initialDateTime = ex_info['DateTime']

                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                baseAsset = ex_info['baseAsset']

                for line in ex_info['filters']:
                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))
 
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))

                currentPrice = round_step_size((float(data['strategy']['order_price'])), tickSize)

                p_contracts = float(contracts)*(((currentPrice - float(initialPrice))/float(initialPrice))*-1)
                p_contracts = round_step_size(p_contracts, stepSize)

                rem_contracts = float(contracts)-p_contracts
                rem_contracts = round_step_size(rem_contracts, stepSize)
                
                order = repay_loan(baseAsset, str(p_contracts))
                tranId = order['tranId']
                
                #---1.2 repay interest

                dfx = (df1.loc[df1['asset']== 'BNB' , :])
                amount = dfx.iloc[0]['interest']
                if float(amount) > 0:
                    order = repay_loan('BNB' ,amount)

                #---1.4 transfer margin to spot

                price = float(data['strategy']['order_price'])
                price = round_step_size(price, tickSize)

                amount = "{:.2f}".format(float(p_contracts) * price )
                print('monto a transferir a spot :',amount)

                transfer_m2s ('USDT',amount)     

                #---1.3 register

                reg_trx = db['registro_trx'] 
                reg_trx.update_one({ '$and': [{"Trade#":tradeCount},{'symbol': symbol}]}, {'$set':{"Contracts":p_contracts}})

                count = db['trade_count'].find_one({'symbol':symbol}) 
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}})  
                count = count['count'] + 1
                
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Short", 
                                    "Signal":"TPs", "DateTime": datetime.now() , 
                                    "Price":currentPrice, "Contracts":p_contracts})

                count = db['trade_count'].find_one({'symbol':symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Entry Short", 
                                    "Signal":"Sell", "DateTime": initialDateTime , 
                                    "Price":initialPrice, "Contracts":(rem_contracts)})
    
    elif data['strategy']['alert_message'] == 'Tailing Stop Long!!!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'short':
                print ('Error: posicion incorrecta para el stop loss')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'flat':
                print ('Error: posicion incorrecta para el stop loss')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'long':
                print('caso 7: Stop Loss Long')

                #---1.1 sell asset  

                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                baseAsset = ex_info['baseAsset']
                
                df = pd.DataFrame((client_bi.get_account())['balances'])
                df = df[df['free'].astype(float) > 0  ]
                df['symbol'] = (df['asset']+'USDT')                  
                
                qty_baseAsset = (df.loc[df['asset']== baseAsset , :])
                contracts = qty_baseAsset.iloc[0]['free'] 
               
                for line in ex_info['filters']:
                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))
                    
                    if line['filterType'] == 'LOT_SIZE':
                        stepSize = float(line.get('stepSize'))
                
                contracts = round_step_size(contracts, stepSize)
                
                order = order_market_sell(symbol, contracts)
                order = order['fills']
 
                for line in order:
                    price = float(line.get('price'))
                    tranId = float(line.get('tradeId'))

                #---1.2 register
                
                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol':symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
               
                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Long", 
                                    "Signal":"Sell", "DateTime": datetime.now() , 
                                    "Price":price, "Contracts":contracts})
                
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"flat"}})

    
    elif data['strategy']['alert_message'] == 'Tailing Stop Short!!!':
        position = (db['current_position']).find_one({"symbol":symbol})

        if  position['position'] == 'long':
                print ('Error: posicion incorrecta para el stop loss')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'flat':
                print ('Error: posicion incorrecta para el stop loss')       
                return {
                'code': 'error', 
                'message': 'something went wrong' 
                 }

        elif position['position'] == 'short':
                print('caso 8: Stop Loss Short')

                #---1.1 repay loan    
            
                df1 = pd.DataFrame((client_bi.get_margin_account())['userAssets'])
                df1 = df1[((df1['borrowed']).astype(float) > 0) | ((df1['free']).astype(float) > 0)]
                df1['symbol'] = (df1['asset']+'USDT')

                df_i = (df1.loc[df1['symbol']== symbol , :])
                amount = df_i.iloc[0]['borrowed']
                asset = df_i.iloc[0]['asset']

                order = repay_loan(asset ,amount)
                tranId = order['tranId']
                
                #---1.2 repay interest

                df_i = (df1.loc[df1['asset']== 'BNB' , :])
                int_amount = df_i.iloc[0]['interest']
                if float(int_amount) > 0:
                    order = repay_loan('BNB' ,int_amount)

                #---1.3 register

                reg_trx = db['registro_trx'] 
                count = db['trade_count'].find_one({'symbol':symbol})
                db['trade_count'].update_one({'$and':[{"count": count['count']},{'symbol':symbol}]}, {'$set':{"count":count['count']+1}}) 
                count = count['count'] + 1
                
                ex_info = (db['exchange_info']).find_one({"symbol":symbol})
                for line in ex_info['filters']:
                    if line['filterType'] == 'PRICE_FILTER':
                        tickSize = float(line.get('tickSize'))           
                
                price = float(data['strategy']['order_price'])
                price = round_step_size(price, tickSize)

                reg_trx.insert_one({"tranId":tranId, "symbol":symbol,"Trade#":count, "Type":"Exit Short", "Signal":"Buy", 
                                "DateTime": datetime.now(), "Price":price,
                                "Contracts":float(amount)})
            
                db['current_position'].update_one({"symbol":symbol}, {'$set':{"position":"flat"}})

                #---1.4 transfer margin to spot

                borrowed = (df1['borrowed'].astype(float)).sum()
                actual_debt = borrowed - float(amount)

                if actual_debt == 0:
                    df_i = (df1.loc[df1['asset']== 'USDT' , :])
                    amount = df_i.iloc[0]['free']
                    transfer_m2s ('USDT',amount)
                else:    
                    amount = "{:.2f}".format(float(amount) * price )
                    transfer_m2s ('USDT',amount) 
    
    else:
        print('data processing failure...fuck!')

    
    order_response = order
    #order_response = 'test'

    if order_response:
        print('the money making machine is alive!')
        return {
            'code': 'success',
            'message': 'order completed'
        }
    else:
        print('chan! something is wrong, not you, the code..')
        return {
            'code': 'error',
            'message': 'order failed' 
        }

