import pickle, numpy as np
s = pickle.load(open('scaler.pkl', 'rb'))
print('Scaler type:', type(s).__name__)
test = np.array([[1.0, 100.0, 50000.0, 5000.0, 10.0, 6.0]])
print('Transform test:', s.transform(test))
if hasattr(s, 'n_features_in_'):
    print('n_features:', s.n_features_in_)
if hasattr(s, 'mean_'):
    print('mean_:', s.mean_)
    print('scale_:', s.scale_)
elif hasattr(s, 'data_min_'):
    print('data_min_:', s.data_min_)
    print('data_max_:', s.data_max_)
