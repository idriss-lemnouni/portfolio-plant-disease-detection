"""Compare colour histograms and a small CPU CNN for potato leaf diagnosis."""

import copy
import json

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score, confusion_matrix, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn

from study_support import REPORT, ROOT, figure, report, save, snapshot, timed_load


SOURCE = "Source: Mohanty et al., original PlantVillage colour images. Lab conditions."
CLASSES = ["early_blight", "healthy", "late_blight"]
SEED = 505


def fingerprint(image):
    patch = Image.fromarray(image).convert("L").resize((9, 8))
    pixels = np.asarray(patch, dtype="int16")
    return int.from_bytes(np.packbits((np.diff(pixels, axis=1) >= 0).ravel()).tobytes())


def load():
    manifest = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8"))
    images, labels, patterns = [], [], []
    for name, row in manifest.items():
        with Image.open(snapshot(name)) as leaf:
            image = np.asarray(leaf.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR))
        images.append(image)
        labels.append(CLASSES.index(row["label"]))
        patterns.append(fingerprint(image))
    if min(np.bincount(labels, minlength=3)) < 75:
        raise ValueError("Insufficient verified images for one or more classes.")
    return np.stack(images), np.array(labels), patterns


def split(labels, patterns):
    rng = np.random.default_rng(SEED)
    parent = list(range(len(labels)))

    def root(index):
        while parent[index] != index:
            index = parent[index]
        return index

    for i, a in enumerate(patterns):
        for j, b in enumerate(patterns[:i]):
            if (a ^ b).bit_count() <= 4:
                parent[root(i)] = root(j)
    result = [[], [], []]
    groups = np.array([root(i) for i in range(len(labels))])
    ambiguous = {g for g in np.unique(groups) if len(set(labels[groups == g])) > 1}
    for label in range(len(CLASSES)):
        clusters = np.unique(groups[labels == label])
        shuffled = rng.permutation([x for x in clusters if x not in ambiguous])
        active = max(2, len(shuffled) // 6)
        for bucket, keys in zip(result, (shuffled[2 * active:], shuffled[active:2 * active], shuffled[:active]), strict=True):
            bucket.extend(np.flatnonzero(np.isin(groups, keys)).tolist())
    return [np.array(values) for values in result], groups


def histogram(images):
    return np.stack([
        np.concatenate([np.histogram(channel, bins=12, range=(0, 256))[0] / (64 * 64)
                        for channel in image.transpose(2, 0, 1)])
        for image in images
    ])


def model():
    return nn.Sequential(
        nn.Conv2d(3, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
        nn.Conv2d(32, 48, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d((3, 3)),
        nn.Flatten(), nn.Dropout(.15), nn.Linear(48 * 9, len(CLASSES)),
    )


def fit(images, labels, train, validation, test):
    torch.set_num_threads(2)
    torch.manual_seed(SEED)
    tensor = torch.from_numpy(images.copy()).permute(0, 3, 1, 2).float() / 255
    mean = tensor[train].mean(dim=(0, 2, 3), keepdim=True)
    std = tensor[train].std(dim=(0, 2, 3), keepdim=True).clamp_min(.01)
    inputs = (tensor - mean) / std
    targets = torch.from_numpy(labels).long()
    cnn = model()
    opt = torch.optim.AdamW(cnn.parameters(), lr=.0025, weight_decay=.001)
    loss_fn = nn.CrossEntropyLoss()
    best, fitted = -1., None
    learning = []
    for epoch in range(1, 23):
        cnn.train()
        losses = []
        for indexes in torch.randperm(len(train)).split(24):
            positions = train[indexes.numpy()]
            patch = inputs[positions]
            if torch.rand(1).item() < .5:
                patch = patch.flip(-1)
            opt.zero_grad()
            loss = loss_fn(cnn(patch), targets[positions])
            loss.backward()
            opt.step()
            losses.append(float(loss.item()))
        cnn.eval()
        with torch.no_grad():
            val = cnn(inputs[validation]).argmax(1).numpy()
        performance = float(f1_score(labels[validation], val, average="macro"))
        learning.append({"epoch": epoch, "training_loss": float(np.mean(losses)), "validation_f1": performance})
        if performance > best:
            best, fitted = performance, copy.deepcopy(cnn.state_dict())
    cnn.load_state_dict(fitted)
    cnn.eval()
    with torch.no_grad():
        probabilities = cnn(inputs[test]).softmax(dim=1).numpy()
        darkened = cnn((tensor[test] * .65 - mean) / std).argmax(1).numpy()
    baseline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=400, random_state=SEED))
    baseline.fit(histogram(images[train]), labels[train])
    return baseline.predict(histogram(images[test])), probabilities, darkened, pd.DataFrame(learning)


def run():
    images, labels, hashes = timed_load(load)
    (train, validation, test), _ = split(labels, hashes)
    reference, probabilities, shifted, curve = fit(images, labels, train, validation, test)
    predictions = probabilities.argmax(axis=1)
    truth = labels[test]
    scores = {key: {"macro_f1": float(f1_score(truth, predicted, average="macro")),
                    "accuracy": float(accuracy_score(truth, predicted))}
              for key, predicted in (("Color histogram", reference), ("CPU CNN", predictions),
                                     ("CPU CNN dimmed", shifted))}
    fig, ax = figure("PlantVillage image support retained by partition", "Class", "Images")
    pd.DataFrame({key: np.bincount(labels[subset], minlength=3) for key, subset in
                  (("Fit", train), ("Validation", validation), ("Test", test))}, index=CLASSES).plot.bar(ax=ax)
    ax.tick_params(axis="x", rotation=0)
    save(fig, "partition-support", SOURCE)
    fig, ax = figure("CPU convolutional network learning diagnostics", "Epoch", "Cross-entropy or F1")
    curve.set_index("epoch").plot(ax=ax)
    save(fig, "learning-diagnostics", SOURCE)
    fig, ax = figure("Withheld leaf-image diagnosis confusion", "Predicted class", "Recorded class")
    ConfusionMatrixDisplay(confusion_matrix(truth, predictions, labels=range(3)), display_labels=CLASSES).plot(ax=ax, colorbar=False)
    save(fig, "leaf-confusion", SOURCE)
    fig, ax = figure("Colour histogram and CNN holdout comparison", "Method and exposure", "Macro F1")
    pd.Series({k: v["macro_f1"] for k, v in scores.items()}).plot.barh(ax=ax, color="#16796b")
    save(fig, "leaf-diagnosis-scores", SOURCE)
    fig, ax = figure("Predicted confidence for right and wrong leaf diagnoses", "CNN confidence", "Images")
    for selected, name in ((predictions == truth, "Correct"), (predictions != truth, "Wrong")):
        ax.hist(probabilities.max(axis=1)[selected], bins=np.linspace(.3, 1, 15), alpha=.58, label=name)
    ax.legend()
    save(fig, "leaf-confidence", SOURCE)
    fig, ax = figure("Effect of controlled dimming by recorded diagnosis", "Class", "Fraction correctly classified")
    pd.DataFrame({"As recorded": [float((predictions[truth == k] == k).mean()) for k in range(3)],
                  "Dimmed to 65%": [float((shifted[truth == k] == k).mean()) for k in range(3)]},
                 index=CLASSES).plot.bar(ax=ax)
    ax.tick_params(axis="x", rotation=0)
    save(fig, "controlled-light-perturbation", SOURCE)
    curve.to_csv(REPORT / "training.csv", index=False, float_format="%.5f")
    report({"verified_images": len(images), "partition_counts": [len(train), len(validation), len(test)],
            "test_classes": dict(zip(CLASSES, np.bincount(truth, minlength=3).tolist(), strict=True)),
            "evaluation": scores, "checkpoint": int(curve.loc[curve.validation_f1.idxmax(), "epoch"])})


if __name__ == "__main__":
    run()
