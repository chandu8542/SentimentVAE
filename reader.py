from pathlib import Path
import pickle
import random
import csv
import numpy as np
import tensorflow as tf
from operator import itemgetter
from config import cfg
import utils


def read_all_csv_rows(filename):

    with open(filename) as f:
        lines = list(csv.reader(f))

    return lines


def word_dropout(sent, vocab):
    ret = []
    for word in sent:
        if random.random() < cfg.word_dropout:
            ret.append(vocab.drop_index)
        else:
            ret.append(word)
    return ret


def pack(batch, vocab):
    '''Pack python-list batches into numpy batches'''
    max_size = max(len(s) for s in batch)
    if len(batch) < cfg.batch_size:
        batch.extend([[] for _ in range(cfg.batch_size - len(batch))])
    leftalign_batch = np.zeros([cfg.batch_size, max_size], dtype=np.int32)
    leftalign_drop_batch = np.zeros([cfg.batch_size, max_size], dtype=np.int32)
    sent_lengths = np.zeros([cfg.batch_size], dtype=np.int32)
    for i, s in enumerate(batch):
        leftalign_batch[i, :len(s)] = s
        leftalign_drop_batch[i, :len(s)] = [s[0]] + word_dropout(s[1:-1], vocab) + \
                                           [s[-1]]
        sent_lengths[i] = len(s)
    return (leftalign_batch, leftalign_drop_batch, sent_lengths)


def row_batch_iter(rows, vocab):

    random.shuffle(rows)
    index = 0
    while (len(rows) - index) >= cfg.batch_size:
        csv_rows = rows[index:index + cfg.batch_size]

        words = [vocab.lookup(row[1].split()) for row in csv_rows]
        labels = [row[0] for row in csv_rows]
        sents, dropped_sents, lengths = pack(words, vocab)
        yield sents, dropped_sents, lengths, labels
        index += cfg.batch_size


class Vocab(object):

    '''Stores the vocab: forward and reverse mappings'''

    def __init__(self, verbose=True):
        self.init_special_tokens()
        self.verbose = verbose

    def init_special_tokens(self):
        self.vocab = ['<pad>', '<sos>', '<eos>', '<unk>', '<drop>']
        self.vocab_lookup = {w: i for i, w in enumerate(self.vocab)}
        self.vocab_count = {w: 0 for w in self.vocab}
        self.unk_index = self.vocab_lookup.get('<unk>')
        self.sos_index = self.vocab_lookup.get('<sos>')
        self.eos_index = self.vocab_lookup.get('<eos>')
        self.drop_index = self.vocab_lookup.get('<drop>')  # for word dropout

    def load_by_csv(self):
        "Load vocabulary from csv files."
        fnames = Path(cfg.data_path).glob('*.csv')
        for fname in fnames:
            if self.verbose:
                print('reading csv:', fname)
            with fname.open('r') as f:
                for row in csv.reader(f):
                    line = row[1]
                    for word in line.split():
                        c = self.vocab_count.get(word, 0)
                        c += 1
                        self.vocab_count[word] = c

        if self.verbose:
            print('Read %d words' % len(self.vocab_count))

        self.prune_vocab(cfg.keep_fraction, self.verbose)

    def prune_vocab(self, keep_fraction):
        sorted_word_counts = sorted(self.vocab_count.items(), key=itemgetter(1),
                                    reverse=True)

        seen_count = 0
        total_count = sum(self.vocab_count.values())
        index = 0
        while seen_count < keep_fraction*total_count:
            seen_count += sorted_word_counts[index][1]
            index += 1
        sorted_word_counts = sorted_word_counts[:index]

        self.init_special_tokens()
        for word, count in sorted_word_counts:
            self.vocab_lookup[word] = len(self.vocab)
            self.vocab.append(word)

        if self.verbose:
            print('Keeping %d words after pruning' % len(self.vocab_lookup))

    def load_from_pickle(self):
        '''Read the vocab from a pickled file'''
        pkfile = cfg.vocab_file
        try:
            if self.verbose:
                print('Loading vocabulary from pickle...')
            with open(pkfile, 'rb') as f:
                self.vocab, self.vocab_lookup = pickle.load(f)
            if self.verbose:
                print('Vocabulary loaded, size:', len(self.vocab))
        except IOError:
            if self.verbose:
                print('Error loading from pickle, attempting parsing.')
            self.load_by_csv()
            with open(pkfile, 'wb') as f:
                pickle.dump([self.vocab, self.vocab_lookup], f, -1)
                if self.verbose:
                    print('Saved pickle file.')

    def lookup(self, words):
        return [self.sos_index] + [self.vocab_lookup.get(w, self.unk_index)
                                   for w in words] + [self.eos_index]


class Reader(object):

    def __init__(self, vocab, verbose=True, load=['train', 'validation', 'test']):
        self.vocab = vocab
        random.seed(0)  # deterministic random
        self.verbose = verbose

        if 'train' in load:
            if self.verbose:
                print('Loading train csv')
            self.train_rows = read_all_csv_rows(cfg.data_path + 'train.csv')
            if self.verbose:
                print('Training samples = %d' % len(self.train_rows))

        if 'validation' in load:
            if self.verbose:
                print('Loading validation csv')
            self.validation_rows = read_all_csv_rows(cfg.data_path + 'validation.csv')
            if self.verbose:
                print('Validation samples = %d' % len(self.validation_rows))

        if 'test' in load:
            if self.verbose:
                print('Loading test csv')
            self.test_rows = read_all_csv_rows(cfg.data_path + 'test.csv')
            if self.verbose:
                print('Testing samples = %d' % len(self.test_rows))

    def training(self):
        '''Read batches from training data'''
        return row_batch_iter(self.train_rows, self.vocab)

    def validation(self):
        '''Read batches from validation data'''
        return row_batch_iter(self.validation_rows, self.vocab)

    def testing(self):
        '''Read batches from testing data'''
        return row_batch_iter(self.test_rows, self.vocab)


def main(_):
    '''Reader tests'''
    vocab = Vocab()
    vocab.load_from_pickle()

    reader = Reader(vocab, load=['test'])
    for sents, dropped_sents, lengths, labels in reader.testing():
        utils.display_sentences(sents, vocab)
        print()

if __name__ == '__main__':
    tf.app.run()
