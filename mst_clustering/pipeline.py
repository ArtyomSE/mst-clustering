import numpy as np

from sklearn.preprocessing import normalize
from typing import Iterator

from mst_clustering.clustering_models import ClusteringModel
from mst_clustering.cpp_adapters import SpanningForest, MstBuilder, DistanceMeasure

import warnings

warnings.filterwarnings('ignore', category=np.VisibleDeprecationWarning)


class Pipeline:
    clustering_models: list[ClusteringModel]
    spanning_forest: SpanningForest = None
    partition: np.ndarray
    noise: np.ndarray

    __models_iterator: Iterator[ClusteringModel]
    __fuzzy_noise_criterion: float
    __min_partition: float
    __data: np.ndarray

    def __init__(self, clustering_models: list[ClusteringModel], min_partition=0.5, fuzzy_noise_criterion=0.1):
        self.clustering_models = clustering_models.copy()
        self.__models_iterator = iter(clustering_models)
        self.__fuzzy_noise_criterion = fuzzy_noise_criterion
        self.__min_partition = min_partition

    def fit(self, data: np.ndarray = None, distance_measure: DistanceMeasure = DistanceMeasure.EUCLIDEAN,
            workers_count: int = 1, initial_partition: np.ndarray = None, spanning_forest: SpanningForest = None,
            n_steps: int = None, use_normalization: bool = False, save_steps: bool = False, step_title: str = "step"):
        if data is not None:
            self.__data = normalize(data.copy()) if use_normalization else data.copy()

        if spanning_forest is not None:
            self.spanning_forest = spanning_forest
        elif self.spanning_forest is None:
            self.spanning_forest = MstBuilder(self.__data.tolist()).build(workers_count, distance_measure)
            assert self.spanning_forest.is_spanning_tree
            all_edges = self.spanning_forest.get_tree_edges(0)
            assert len(all_edges) == self.__data.shape[0] - 1

        partition = initial_partition
        self.noise = np.zeros(self.__data.shape[0])

        for step in range(n_steps if n_steps is not None else len(self.clustering_models)):
            try:
                model = next(self.__models_iterator)
            except StopIteration:
                break

            partition = model(data=self.__data, forest=self.spanning_forest, workers=workers_count, partition=partition)
            partition = self.__clean_noise(partition)
            self.partition = partition

            if save_steps:
                self.spanning_forest.save(f"{step_title}-spanning-forest#{step}")
                np.save(f"{step_title}-labels#{step}", self.labels)

        return self

    @property
    def labels(self) -> np.ndarray:
        labels = np.argmax(np.vstack((self.noise, self.partition)), axis=0)
        return labels

    @property
    def clusters_count(self) -> np.ndarray:
        return (~np.all(self.partition == 0, axis=1)).shape[0]

    def __clean_noise(self, partition):
        labels_counts = np.sum(partition > self.__min_partition, axis=1)
        for index, count in enumerate(labels_counts):
            if count / self.__data.shape[0] <= self.__fuzzy_noise_criterion:
                self.noise[partition[index] > 0] = 1
                partition[index][partition[index] > 0] = 0

        return partition
