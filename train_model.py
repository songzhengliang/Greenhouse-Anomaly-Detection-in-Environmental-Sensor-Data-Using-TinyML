import emlearn
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import pickle
import pandas as pd
# Load the dataset
df = pd.read_csv('greenhouse_air_quality_dataset.csv')
df_3 = df.iloc[:,:3]
X = df_3.to_numpy()
df_1 = df.iloc[:,-1]
y = df_1.to_numpy()

# Train a Random Forest Classifier
model = RandomForestClassifier(n_estimators=10, max_depth=5, random_state=50)
model.fit(X, y)
# Save the model to a file
with open('model.pkl', 'wb') as f:
    pickle.dump(model, f)

# Convert the model to C code using emlearn
c_model = emlearn.convert(model, method='inline')
c_model.save(file = 'model.csv', name = 'model', format='csv')

