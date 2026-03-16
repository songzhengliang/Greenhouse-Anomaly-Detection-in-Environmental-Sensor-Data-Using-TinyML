import emlearn_trees
import array

model = emlearn_trees.new(10, 100, 100)

# Load the model from the CSV file
with open('model.csv', 'r') as f:
    emlearn_trees.load_model(model, f)

def predict(co2, temp, humidity):
    # Make a prediction using the loaded model
    input_data = array.array('h', [int(co2), int(temp), int(humidity)])
    output = array.array('f', range(model.outputs()))
    model.predict(input_data, output)
    predict_class = 0
    max_prob = output[0]
    for i in range(1, len(output)):
        if output[i] > max_prob:
            max_prob = output[i]
            predict_class = i
    return predict_class, max_prob

# Example usage
print(predict(500, 23.0, 48.0))  # Should predict class 1 (优秀)
print(predict(1200, 25.0, 52.0)) # Should predict class 2 (一般)
print(predict(1600, 28.0, 57.0)) # Should predict class 3 (较差)
print(predict(2500, 31.0, 62.0)) # Should predict class 4 (差)