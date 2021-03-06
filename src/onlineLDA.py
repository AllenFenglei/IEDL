# coding=utf-8
"""Online Latent Dirichlet allocation using collapsed Gibbs sampling"""

from __future__ import absolute_import, division, unicode_literals  # noqa
import logging
import sys
from sklearn.svm import SVC
from sklearn.model_selection import StratifiedShuffleSplit
import numpy as np
import numbers

import _lda

logger = logging.getLogger('lda')

PY2 = sys.version_info[0] == 2
if PY2:
    range = xrange


class OLDA:
    """Latent Dirichlet allocation using collapsed Gibbs sampling

    Parameters
    ----------
    n_topics : int
        Number of topics

    n_iter : int, default 2000
        Number of sampling iterations

    alpha : float, default 0.1
        Dirichlet parameter for distribution over topics

    eta : float, default 0.01
        Dirichlet parameter for distribution over words

    random_state : int or RandomState, optional
        The generator used for the initial topics.

    Attributes
    ----------
    `components_` : array, shape = [n_topics, n_features]
        Point estimate of the topic-word distributions (Phi in literature)
    `topic_word_` :
        Alias for `components_`
    `nzw_` : array, shape = [n_topics, n_features]
        Matrix of counts recording topic-word assignments in final iteration.
    `ndz_` : array, shape = [n_samples, n_topics]
        Matrix of counts recording document-topic assignments in final iteration.
    `doc_topic_` : array, shape = [n_samples, n_features]
        Point estimate of the document-topic distributions (Theta in literature)
    `nz_` : array, shape = [n_topics]
        Array of topic assignment counts in final iteration.

    Examples
    --------
    >>> import numpy
    >>> X = numpy.array([[1,1], [2, 1], [3, 1], [4, 1], [5, 8], [6, 1]])
    >>> import lda
    >>> model = lda.LDA(n_topics=2, random_state=0, n_iter=100)
    >>> model.fit(X) #doctest: +ELLIPSIS +NORMALIZE_WHITESPACE
    LDA(alpha=...
    >>> model.components_
    array([[ 0.85714286,  0.14285714],
           [ 0.45      ,  0.55      ]])
    >>> model.loglikelihood() #doctest: +ELLIPSIS
    -40.395...

    References
    ----------
    Blei, David M., Andrew Y. Ng, and Michael I. Jordan. "Latent Dirichlet
    Allocation." Journal of Machine Learning Research 3 (2003): 993–1022.

    Griffiths, Thomas L., and Mark Steyvers. "Finding Scientific Topics."
    Proceedings of the National Academy of Sciences 101 (2004): 5228–5235.
    doi:10.1073/pnas.0307752101.

    Wallach, Hanna, David Mimno, and Andrew McCallum. "Rethinking LDA: Why
    Priors Matter." In Advances in Neural Information Processing Systems 22,
    edited by Y.  Bengio, D. Schuurmans, J. Lafferty, C. K. I. Williams, and A.
    Culotta, 1973–1981, 2009.

    Buntine, Wray. "Estimating Likelihoods for Topic Models." In Advances in
    Machine Learning, First Asian Conference on Machine Learning (2009): 51–64.
    doi:10.1007/978-3-642-05224-8_6.

    """

    def __init__(self, n_topics, n_iter=2000, random_state=None,
                 refresh=10, window_size=1, theta=0.5):
        self.n_topics = n_topics
        self.n_iter = n_iter
        self.window_size = window_size
        # if random_state is None, check_random_state(None) does nothing
        # other than return the current numpy RandomState
        self.random_state = random_state
        self.refresh = refresh
        self.alpha_m = None
        self.eta_m = None
        self.eta_l = None
        self.alpha_sum = None
        self.eta_sum = None
        self.theta = theta
        self.alpha = 0.1
        self.B = []
        self.A = []
        self.loglikelihoods_pred = []
        self.loglikelihoods_train = []
        self.ll = -1
        # random numbers that are reused
        rng = self.check_random_state(random_state)
        self._rands = rng.rand(1024**2 // 8)  # 1MiB of random variates

        # configure console logging if not already configured
        if len(logger.handlers) == 1 and isinstance(logger.handlers[0], logging.NullHandler):
            logging.basicConfig(level=logging.INFO)

    def fit(self, X, decay_flag, SVM_flag, alpha=0.1, eta=0.01, y=None):
        """Fit the model with X.

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            Training data, where n_samples in the number of samples
            and n_features is the number of features. Sparse matrix allowed.

        Returns
        -------
        self : object
            Returns the instance itself.
        """
        # =================== online process===================

        # split X into time slots, feed into LDA model with alpha, beta matrix and B
        for t, x in enumerate(X):
            # if t == len(X) - 1:     # skip the last batch
            #     return self
            D, W = x.shape

            n_topics = self.n_topics
            if t == 0:
                eta_m = np.full((n_topics, W), eta).astype(np.float64)
            else:
                eta_m = self.soft_align(self.B, self.window_size, self.theta, decay_flag).astype(np.float64)
            alpha_m = np.full((D, n_topics), alpha).astype(np.float64)
            self.alpha_m = alpha_m
            self.eta_m = eta_m
            self.eta_l = eta_m
            self.alpha_sum = np.sum(alpha_m, 1)
            self.eta_sum = np.sum(eta_m, 1)
            self.alpha = alpha
            # fit the model
            self._fit(x, alpha_m, eta_m)
            # test the model
            # if t != len(X) - 1:
            #     ll_pred = self.estimate_ll(X[t+1])
            #     self.loglikelihoods_pred.append(ll_pred)
            self.loglikelihoods_train.append(self.ll)
            self.B.append(self.topic_word_)
            self.A.append(self.doc_topic_)
            #totally 12 slices
            #print(self.B[0].shape)#(8, 10000) 8 is the topic number 1*10000
            #print(self.A[0])#(4565, 8) 4565 is the sentence number
            #self.test_SVM(self.A[0],"../dataset/rawdata/test_label.txt")
        #c=np.vstack((self.A[0],self.A[1]))
        #print(c.shape)
        #print(self.A[2].shape)
        if SVM_flag == 1:
            self.test_SVM(self.A[2],"../dataset/rawdata/test_label.txt")
        #self.test_SVM(self.A[2],"../dataset/software_label.txt")    #test for solfware     !!!!!!!!!!!!!!
        return self

    def soft_align(self, B, window_size, theta, decay_flag):
        """
        Soft alignment to produce a soft weight sum of B according to window size
        """
        eta = B[-1]
        eta_new = np.zeros(eta.shape)
        if decay_flag == 0:
            logging.info("Using similarities.")
            weights = self.softmax(eta, B, window_size)
        else:
            logging.info("Using exponential decay.")
            weights = self.Exponential_Decay(eta, B, window_size)
        for i in range(window_size):
            if i > len(B)-1:
                break
            B_i = B[-i-1] * weights[i][:, np.newaxis]
            eta_new += B_i
        eta_new = theta * self.eta_l + (1 - theta) * eta_new
        return eta_new

    def softmax(self, eta, B, window_size): #maybe here!
        prods = []
        for i in range(window_size):
            if i > len(B)-1:
                break
            prods.append(np.einsum('ij,ij->i', eta, B[-i-1]))   #eta*B, every element times each
            #print(np.einsum('ij,ij->i', eta, B[-i-1]))
            #print(B[-i-1].shape)#(8, 10000)
            #print(eta.shape)#(8, 10000)
        weights = np.exp(np.array(prods))
        #print(len(weights)) #window_size
        #print(weights[0].shape) #8
        #print(weights[0])   #[ 1.00263107  1.00360126  1.00329721  1.00297992  1.01121932  1.00732886  1.00261926  1.01368105]
        # weights = np.ones(weights.shape)            # compare to uniform
        n_weights = weights / np.sum(weights, 0)  # column normalize
        #print(n_weights)
        
        #[[ 0.33381404  0.33574404  0.33377568  0.3337511   0.33380458  0.33383676   0.33399144  0.33362642]
        # [ 0.33305652  0.33212032  0.33305132  0.33308513  0.33307685  0.33294443   0.33296081  0.33313675]
        # [ 0.33312945  0.33213563  0.333173    0.33316377  0.33311857  0.33321881   0.33304775  0.33323683]]
        return n_weights

    def Exponential_Decay(self, eta, B, window_size):
        decay_k = 1.0
        decay_mu = []
        prods = []
        for i in range(window_size):
            if i > len(B)-1:
                break
            decay_mu.append(np.exp(-decay_k*(window_size-i-1)))
            prods.append(np.einsum('ij,ij->i', eta, B[-i-1]))   #eta*B, every element times each
            #print(B[-i-1].shape)#(8, 10000)
            #print(eta.shape)#(8, 10000)
        weights = np.exp(np.array(prods))
        for i, mu in enumerate(decay_mu):
            weights[i] = mu * weights[i]
            #print(weights[i])
            #print(mu)
            #print(temp)
        #print(len(weights)) #window_size
        #print(weights[0].shape) #8
        #print(weights[0])   #[ 1.00263107  1.00360126  1.00329721  1.00297992  1.01121932  1.00732886  1.00261926  1.01368105]
        # weights = np.ones(weights.shape)            # compare to uniform
        n_weights = weights / np.sum(weights, 0)  # column normalize
        #print(n_weights)
        
        #[[ 0.18653837  0.1865785   0.18666854  0.18725954  0.18683939  0.18660835   0.18821754  0.18675937]
        #[ 0.30712336  0.30695458  0.30711745  0.30811781  0.30709808  0.30705398   0.30602268  0.30722897]
        #[ 0.50633827  0.50646693  0.506214    0.50462266  0.50606253  0.50633766   0.50575978  0.50601165]]
        return n_weights

    def estimate_ll(self, X):
        doc_topic = self.transform(X)
        ll_pred = self.compute_loglikelihood(doc_topic, self.topic_word_, X)
        logging.info("test perplexity: %f"%ll_pred)
        return ll_pred

    # return the +ELLIPSIS
    def compute_loglikelihood(self, doc_topic, topic_word, X):
        temp = np.log(np.dot(doc_topic, topic_word))
        return np.sum(X.multiply(temp))

    def fit_transform(self, X, y=None):
        """Apply dimensionality reduction on X

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features. Sparse matrix allowed.

        Returns
        -------
        doc_topic : array-like, shape (n_samples, n_topics)
            Point estimate of the document-topic distributions

        """

        if isinstance(X, np.ndarray):
            # in case user passes a (non-sparse) array of shape (n_features,)
            # turn it into an array of shape (1, n_features)
            X = np.atleast_2d(X)
        self._fit(X)
        return self.doc_topic_

    def transform(self, X, max_iter=20, tol=1e-16):
        """Transform the data X according to previously fitted model

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            New data, where n_samples in the number of samples
            and n_features is the number of features.
        max_iter : int, optional
            Maximum number of iterations in iterated-pseudocount estimation.
        tol: double, optional
            Tolerance value used in stopping condition.

        Returns
        -------
        doc_topic : array-like, shape (n_samples, n_topics)
            Point estimate of the document-topic distributions

        Note
        ----
        This uses the "iterated pseudo-counts" approach described
        in Wallach et al. (2009) and discussed in Buntine (2009).

        """
        if isinstance(X, np.ndarray):
            # in case user passes a (non-sparse) array of shape (n_features,)
            # turn it into an array of shape (1, n_features)
            X = np.atleast_2d(X)
        doc_topic = np.empty((X.shape[0], self.n_topics))
        WS, DS = self.matrix_to_lists(X)
        # TODO: this loop is parallelizable
        for d in np.unique(DS):
            doc_topic[d] = self._transform_single(WS[DS == d], max_iter, tol)
        return doc_topic

    def _transform_single(self, doc, max_iter, tol):
        """Transform a single document according to the previously fit model

        Parameters
        ----------
        X : 1D numpy array of integers
            Each element represents a word in the document
        max_iter : int
            Maximum number of iterations in iterated-pseudocount estimation.
        tol: double
            Tolerance value used in stopping condition.

        Returns
        -------
        doc_topic : 1D numpy array of length n_topics
            Point estimate of the topic distributions for document

        Note
        ----

        See Note in `transform` documentation.

        """
        PZS = np.zeros((len(doc), self.n_topics))
        for iteration in range(max_iter + 1): # +1 is for initialization
            PZS_new = self.components_[:, doc].T
            PZS_new *= (PZS.sum(axis=0) - PZS + self.alpha)
            PZS_new /= PZS_new.sum(axis=1)[:, np.newaxis] # vector to single column matrix
            delta_naive = np.abs(PZS_new - PZS).sum()
            logger.debug('transform iter {}, delta {}'.format(iteration, delta_naive))
            PZS = PZS_new
            if delta_naive < tol:
                break
        theta_doc = PZS.sum(axis=0) / PZS.sum()
        assert len(theta_doc) == self.n_topics
        assert theta_doc.shape == (self.n_topics,)
        return theta_doc

    def _fit(self, X, alpha, eta):
        """Fit the model to the data X

        Parameters
        ----------
        X: array-like, shape (n_samples, n_features)
            Training vector, where n_samples in the number of samples and
            n_features is the number of features. Sparse matrix allowed.
        """
        random_state = self.check_random_state(self.random_state)
        rands = self._rands.copy()
        self._initialize(X)


        for it in range(self.n_iter):
            # FIXME: using numpy.roll with a random shift might be faster
            random_state.shuffle(rands)
            if it % self.refresh == 0:
                ll = self.loglikelihood()
                logger.info("<{}> log likelihood: {:.0f}".format(it, ll))
                # keep track of loglikelihoods for monitoring convergence
                self.loglikelihoods_.append(ll)
            self._sample_topics(rands)
        self.ll = self.loglikelihood()
        logger.info("<{}> log likelihood: {:.0f}".format(self.n_iter - 1, self.ll))
        # note: numpy /= is integer division
        self.components_ = (self.nzw_ + eta).astype(float)
        self.components_ /= np.sum(self.components_, axis=1)[:, np.newaxis]
        self.topic_word_ = self.components_
        self.doc_topic_ = (self.ndz_ + alpha).astype(float)
        self.doc_topic_ /= np.sum(self.doc_topic_, axis=1)[:, np.newaxis]

        # delete attributes no longer needed after fitting to save memory and reduce clutter
        del self.WS
        del self.DS
        del self.ZS
        return self

    def _initialize(self, X):
        D, W = X.shape
        N = int(X.sum())
        n_topics = self.n_topics
        n_iter = self.n_iter
        logger.info("n_documents: {}".format(D))
        logger.info("vocab_size: {}".format(W))
        logger.info("n_words: {}".format(N))
        logger.info("n_topics: {}".format(n_topics))
        logger.info("n_iter: {}".format(n_iter))

        self.nzw_ = nzw_ = np.zeros((n_topics, W), dtype=np.intc)
        self.ndz_ = ndz_ = np.zeros((D, n_topics), dtype=np.intc)
        self.nz_ = nz_ = np.zeros(n_topics, dtype=np.intc)

        self.WS, self.DS = WS, DS = self.matrix_to_lists(X)
        self.ZS = ZS = np.empty_like(self.WS, dtype=np.intc)
        np.testing.assert_equal(N, len(WS))
        for i in range(N):
            w, d = WS[i], DS[i]
            z_new = i % n_topics
            ZS[i] = z_new
            ndz_[d, z_new] += 1
            nzw_[z_new, w] += 1
            nz_[z_new] += 1
        self.loglikelihoods_ = []

    def loglikelihood(self):
        """Calculate complete log likelihood, log p(w,z)

        Formula used is log p(w,z) = log p(w|z) + log p(z)
        """
        nzw, ndz, nz = self.nzw_, self.ndz_, self.nz_
        alpha_m = self.alpha_m
        eta_m = self.eta_m
        alpha_sum = self.alpha_sum
        eta_sum = self.eta_sum
        nd = np.sum(ndz, axis=1).astype(np.intc)
        return _lda._loglikelihood(nzw, ndz, nz, nd, alpha_m, eta_m, alpha_sum, eta_sum)

    def _sample_topics(self, rands):
        """Samples all topic assignments. Called once per iteration."""
        n_topics, vocab_size = self.nzw_.shape
        alpha = self.alpha_m    #np.repeat(self.alpha, n_topics).astype(np.float64)
        eta = self.eta_m        #np.repeat(self.eta, vocab_size).astype(np.float64)
        eta_sum = self.eta_sum
        _lda._sample_topics(self.WS, self.DS, self.ZS, self.nzw_, self.ndz_, self.nz_,
                                alpha, eta, eta_sum, rands)
        # self.sample_topics_py(self.WS, self.DS, self.ZS, self.nzw_, self.ndz_, self.nz_,
        #                         alpha, eta, eta_sum, rands)

    def searchsorted_py(self, arr, length, value):
        """Bisection search (c.f. numpy.searchsorted)

        Find the index into sorted array `arr` of length `length` such that, if
        `value` were inserted before the index, the order of `arr` would be
        preserved.
        """
        imin = 0
        imax = length
        while imin < imax:
            imid = imin + ((imax - imin) >> 2)
            if value > arr[imid]:
                imin = imid + 1
            else:
                imax = imid
        return imin

    def sample_topics_py(self, WS, DS, ZS, nzw, ndz, nz, alpha, eta, eta_sum, rands):

        N = WS.shape[0]

        n_rand = rands.shape[0]

        n_topics = nz.shape[0]
        # cdef double eta_sum = 0

        dist_sum = np.zeros(n_topics, dtype=float)

        # for i in range(eta.shape[0]):
        #    eta_sum += eta[i]

        for i in range(N):
            w = WS[i]
            d = DS[i]
            z = ZS[i]

            nzw[z, w] -= 1
            ndz[d, z] -= 1
            nz[z] -= 1

            dist_cum = 0
            for k in range(n_topics):
                # eta is a double so cdivision yields a double
                dist_cum += (nzw[k, w] + eta[k, w]) / (nz[k] + eta_sum[k]) * (ndz[d, k] + alpha[d, k])
                dist_sum[k] = dist_cum

            r = rands[i % n_rand] * dist_cum  # dist_cum == dist_sum[-1]
            z_new = self.searchsorted_py(dist_sum, n_topics, r)

            ZS[i] = z_new
            nzw[z_new, w] += 1
            ndz[d, z_new] += 1
            nz[z_new] += 1

    def check_random_state(self, seed):
        if seed is None:
            # i.e., use existing RandomState
            return np.random.mtrand._rand
        if isinstance(seed, (numbers.Integral, np.integer)):
            return np.random.RandomState(seed)
        if isinstance(seed, np.random.RandomState):
            return seed
        raise ValueError("{} cannot be used as a random seed.".format(seed))

    def matrix_to_lists(self, doc_word):
        """Convert a (sparse) matrix of counts into arrays of word and doc indices

        Parameters
        ----------
        doc_word : array or sparse matrix (D, V)
            document-term matrix of counts

        Returns
        -------
        (WS, DS) : tuple of two arrays
            WS[k] contains the kth word in the corpus
            DS[k] contains the document index for the kth word

        """
        if np.count_nonzero(doc_word.sum(axis=1)) != doc_word.shape[0]:
            logger.warning("all zero row in document-term matrix found")
        if np.count_nonzero(doc_word.sum(axis=0)) != doc_word.shape[1]:
            logger.warning("all zero column in document-term matrix found")
        sparse = True
        try:
            # if doc_word is a scipy sparse matrix
            doc_word = doc_word.copy().tolil()
        except AttributeError:
            sparse = False

        if sparse and not np.issubdtype(doc_word.dtype, int):
            raise ValueError("expected sparse matrix with integer values, found float values")

        ii, jj = np.nonzero(doc_word)
        if sparse:
            ss = tuple(doc_word[i, j] for i, j in zip(ii, jj))
        else:
            ss = doc_word[ii, jj]

        n_tokens = int(doc_word.sum())
        DS = np.repeat(ii, ss).astype(np.intc)
        WS = np.empty(n_tokens, dtype=np.intc)
        startidx = 0
        for i, cnt in enumerate(ss):
            cnt = int(cnt)
            WS[startidx:startidx + cnt] = jj[i]
            startidx += cnt
        return WS, DS

    def lists_to_matrix(self, WS, DS):
        """Convert array of word (or topic) and document indices to doc-term array

        Parameters
        -----------
        (WS, DS) : tuple of two arrays
            WS[k] contains the kth word in the corpus
            DS[k] contains the document index for the kth word

        Returns
        -------
        doc_word : array (D, V)
            document-term array of counts

        """
        D = max(DS) + 1
        V = max(WS) + 1
        doc_word = np.empty((D, V), dtype=np.intc)
        for d in range(D):
            for v in range(V):
                doc_word[d, v] = np.count_nonzero(WS[DS == d] == v)
        return doc_word

    def read_labels_deeplearning(self, path):
        out = []
        f = open(path, 'r')
        for i in f:
            if i == "Image\n":
                out.append(0)
            if i == "NLP\n":
                out.append(1)
            #if i == "unsupervised-learning\n":
            #    out.append(2)
            #if i == "CNN\n":
            #    out.append(3)
            #if i == "Tensorflow\n":
            #    out.append(2)
            if i == "Gaming\n":
                out.append(2)
            if i == "Game-ai\n":
                out.append(2)
            if i == "Self-driving\n":
                out.append(3)
            if i == "Programming-languages\n":
                out.append(4)
            if i == "Reinforcement-learning\n":
                out.append(5)
            #if i == "Voice-recognition\n":
            #    out.append(8)
        f.close()
        return out

    def read_labels_software(self, path):
        out = []
        f = open(path, 'r')
        for i in f:
            if i[:5] == "Debug":
                if i[10:15] == "runti":
                    out.append(0)
                elif i[10:15] == "train":
                    out.append(0)
                elif i[10:15] == "perfo":
                    out.append(0)
                else:
                    print(i)
                    print("")
            elif i[:5] == "Imple":
                if i[15:20] == "funct":
                    out.append(1)
                else:
                    out.append(1)
            elif i[:5] == "Compr":
                out.append(1)
            elif i[:5] == "insta":
                out.append(2)
            elif i[:5] == "Archi":
                out.append(2)
            elif i[:5] == "build":
                out.append(0)
            else:
                print(i)
                print("")
        f.close()
        return out

    def accuracy(self, y, predict):
        num = 0
        for i in range(len(y)):
            if y[i] == predict[i]:
                num += 1
        return num/len(y)

    def test_SVM(self, X, y_path):
        y = np.array(self.read_labels_deeplearning(y_path))
        #y = np.array(self.read_labels_software(y_path))
        X = np.array(X)
        #print y
        #print X
        #print len(y)
        sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=1)
        for train_index, test_index in sss.split(X, y):
            #print "TRAIN:", train_index, "TEST:", test_index
            train, train_label = X[train_index], y[train_index]
            test, test_label = X[test_index], y[test_index]

        clf = SVC(C=1, kernel='rbf', gamma=10, decision_function_shape='ovr', random_state=23)#23  .705
        clf.fit(train, train_label)

        print clf.score(train, train_label)
        #predict_train = clf.predict(train)
        #print self.accuracy(train_label, predict_train)
        print clf.score(test, test_label)
        predict_test = clf.predict(test)
        #print self.accuracy(test_label, predict_test)
        self.pre_recall(test_label, predict_test, 6)

    def pre_recall(self, y_true, y_pred, topic_num):
        precision = []
        recall = []
        f1 = []
        total = 0
        if len(y_true) != len(y_pred):
            logger.error("y_pred and y_true should have the same length!")
        matrix = np.zeros((topic_num, topic_num))
        for row, col in zip(y_pred, y_true):
            matrix[row][col] = matrix[row][col] + 1
        print matrix
        #for x in range(topic_num):
        #    total = total + matrix[x][x]
        #print "precision:",total/len(y_pred)
        for x in range(topic_num):
            print "topic "+str(x)
            precision.append(matrix[x][x]/matrix.sum(axis=1)[x])
            print "precision: ", matrix[x][x]/matrix.sum(axis=1)[x]
            recall.append(matrix[x][x]/matrix.sum(axis=0)[x])
            print "recall: ", matrix[x][x]/matrix.sum(axis=0)[x]
            f1.append(2*precision[x]*recall[x]/(precision[x]+recall[x]))
            print "f1: ", f1[x]

        