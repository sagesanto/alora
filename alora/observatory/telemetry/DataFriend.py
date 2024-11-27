import pandas as pd, numpy as np, matplotlib.pyplot as plt, seaborn as sns
import requests, json, os, sys, time, datetime, re, random, math, pickle

class DataFriend:
    def __init__(self,api_url="http://localhost:5000/api"):
        self.api_url = api_url
    
    def sql_query(self,query, asDf = True):
        data = requests.get(self.api_url,json={"query":query}).json()
        print("received response")
        if data["error"]:
            raise ValueError(f"Response came back with error {data['error']}")
        r = data["result"]
        if asDf:
            r = pd.DataFrame(r)
            for col in r.columns:
                r[col] = pd.to_numeric(r[col],errors="ignore")
                # r["Timestamp"] = pd.to_datetime(r["Timestamp"],unit="s")
                r = r.sort_values(by="Timestamp")
        return r

# example usage:
if __name__ == '__main__':

    friend = DataFriend()

    SQL_QUERY = "SELECT * FROM SensorUpTime"
    
    df = friend.sql_query(SQL_QUERY)
    print("received dataframe, start plotting...")


    fig, ax = plt.subplots()
    for i, col in enumerate(df.columns):
        if col == "Timestamp":
            continue
        ax.scatter(df["Timestamp"],df[col]*(i+1),label=col)
    ax.scatter(df["Timestamp"],[0]*len(df["Timestamp"]),label="Telemetry Server")
    plt.legend()
    plt.title("Sensor Up Time")
    plt.xlabel("Timestamp")
    plt.yticks([])


    plt.show()
