# coding: utf-8

"""
Semi-superised LDA
"""

import numpy as np
import random
import math
from scipy.special import gamma,gammaln
from scipy import weave
import sys, os


stop = set(l.strip() for l in file("/home/top/downloads/multi-task-review/sorted_data/stopwords"))

import re
wre = re.compile(r"(\w)+")
def get_words(text):
    "A simple tokenizer"
    l = 0
    while l < len(text):
        s = wre.search(text,l)
        try:
            st = text[s.start():s.end()].lower()
            if not st in stop:
                yield st 
            l = s.end()
        except:
            break

def categorical2(probs):
    return np.argmax(np.random.multinomial(1,probs))


def parse_file(reviews, bp, dire, p, l, fname):
    f = os.path.join(bp,dire,fname)
    in_review = False
    text = ""
    for line in file(f):
        if in_review:
            if line.strip() == "</review_text>":
                in_review = False
                reviews.append((p, l, text))
                text = ""
            else:
                text += " " + line
        else:
            if line.strip() == "<review_text>":
                in_review = True
    return reviews

def parse_reviews(bp):
    reviews = []
    for p,dire in enumerate(os.listdir(bp)):
        if not "." in dire and not "stopwords" in dire:
            parse_file(reviews, bp, dire, p, "n", "negative.review")
            parse_file(reviews, bp, dire, p, "p", "positive.review")
            parse_file(reviews, bp, dire, p, "u", "unlabeled.review")
    return reviews
    


class OpinionSampler(object):
    def __init__(self, reviews, nops):
        print "init"
        random.shuffle(reviews)
        self.product = [r[0] for r in reviews]
        self.all_products = list(sorted(set(self.product)))
        self.mprod = max(self.all_products)+1
        self.label = [r[1] for r in reviews]
        self.text = [r[2] for r in reviews]
        print "init 2"
        self.docs = []
        self.reverse_map = {}
        self.all_words = []
        for t in self.text:
            doc = []
            for w in get_words(t):
                if not w in self.reverse_map:
                    self.reverse_map[w] = len(self.all_words)
                    self.all_words.append(w)
                doc.append(self.reverse_map[w])
            self.docs.append(doc)
        print "init 3"
        self.Ndocuments = len(self.docs)
        self.Nwords = len(self.all_words)
        self.Nops = nops
        self.ops = np.zeros((nops,len(self.all_words)))
        self.prods = [np.zeros(len(self.all_words)) for i in xrange(self.mprod)]
        self.generic = np.zeros(len(self.all_words))
        self.alpha = 0.0001
        self.beta = 0.001
        self.initialize()


    def initialize(self):
        print "init 4"
        self.assign_ops = [random.randint(0, len(self.ops)-1) for i in self.docs]
        self.assign_words = []
        print "init 5"
        ps = np.array([1., 1., 1.])/3.
        for d in xrange(self.Ndocuments):
            ass = []
            for i,w in enumerate(self.docs[d]):
                t = categorical2(ps)
                ass.append(t)
                if t == 1:
                    self.ops[self.assign_ops[d]][w] += 1
                elif t == 0:
                    self.prods[self.product[d]][w] += 1
                else:
                    self.generic[w] += 1
            self.assign_words.append(ass)
        print "init 6"

    def w_cond_dist(self, d,w):
        op = self.ops[self.assign_ops[d]]
        prod = self.prods[self.product[d]]
        generic = self.generic
        ww = self.docs[d][w]
        if self.assign_words[d][w] == 1:
            op[ww] -= 1
        elif self.assign_words[d][w] == 0:
            prod[ww] -= 1
        else:
            generic[ww] -= 1
        ps = np.zeros(3)
        ps[1] = (op[ww]+self.alpha)/(np.sum(op)+self.Nwords*self.alpha)
        ps[0] = (prod[ww]+self.alpha)/(np.sum(prod)+self.Nwords*self.alpha)
        ps[2] = (generic[ww]+self.alpha)/(np.sum(generic)+self.Nwords*self.alpha)
        ps /= np.sum(ps)
        t = categorical2(ps)
        self.assign_words[d][w] = t
        if self.assign_words[d][w] == 1:
            op[ww] += 1
        elif self.assign_words[d][w] == 0:
            prod[ww] += 1
        else:
            generic[ww] += 1

    def rel_words(self, d):
        rwd = np.zeros(len(self.all_words))
        for i,w in enumerate(self.assign_words[d]):
            if w == 1:
                rwd[self.docs[d][i]] += 1
        return rwd

    def c_cond_dist(self, d):
        rwd = self.rel_words(d)
        self.ops[self.assign_ops[d]] -= rwd

        ps = np.zeros(len(self.ops))
        for i,op in enumerate(self.ops):
            opa = op+self.alpha
            num = np.log(opa)
            den = np.log(np.sum(opa))
            ps[i] = np.sum(rwd*(num-den))
        ps /= np.sum(ps)
        nop = categorical2(ps)
        self.assign_ops[d] = nop
        self.ops[nop] += rwd
        

    def iterate(self):
        for document in xrange(self.Ndocuments):
            if document % 1000 == 0:
                print "document", document, self.Ndocuments
            self.c_cond_dist(document)
            for i in xrange(len(self.docs[document])):
                self.w_cond_dist(document, i)

    def likelihood(self):
        lik = 0
        for d in xrange(self.Ndocuments):
            for i,w in enumerate(self.docs[d]):
                if self.assign_words[d][i] == 1:
                    ps = self.ops[self.assign_ops[d]]
                elif self.assign_words[d][i] == 0:
                    ps = self.prods[self.product[d]]
                else:
                    ps = self.generic
                lik += np.log((ps[w]+self.alpha)/np.sum(ps+self.alpha))
                if lik != lik:
                    print "nan, shit"
                    print str(ps), ps[w]+self.alpha/np.sum(ps+self.alpha)
                    return 0.
        return lik

    def run(self,nsamples):
        "The sampler itself."
        old_lik = -np.inf
        iteration = 0
        for i in xrange(nsamples):
            iteration += 1
            self.iterate()
            self.print_op_proportions()
            self.print_prod_proportions()
            print "pre-lik"
            lik = self.likelihood()
            #self.print_topic_proportions()
            print lik

    def print_op_proportions(self):
        props = [{"n":0, "p":0, "u":0} for o in self.ops]
        for d in xrange(len(self.docs)):
            props[self.assign_ops[d]][self.label[d]] += 1
        p2 = []
        for i,p in enumerate(props):
            ps = self.ops[i]+self.alpha
            norm = np.sum(ps)
            top_k = np.argsort(-ps)[:20]
            print
            for t in top_k:
                print self.all_words[t], ps[t]/float(norm)
            c_p = p["p"]
            c_n = p["n"]
            c_u = p["u"]
            c_t = float(c_p+c_n+c_u)
            if c_t == 0: continue
            print "op",
            print "r %5f" %(c_p/float(c_n)), "p %5f"%(c_p/c_t), "n %5f"%(c_n/c_t),
            print "u %5f"%(c_u/c_t), "t", c_t


    def print_prod_proportions(self):
        p2 = []
        cr = np.zeros(len(self.prods))
        cp = np.zeros(len(self.prods))
        cg = np.zeros(len(self.prods))
        cc = [cp,cr,cg]
        for i in xrange(len(self.docs)):
            for j in xrange(len(self.docs[i])):
                cc[self.assign_words[i][j]][self.product[i]] += 1
        for i,p in enumerate(self.prods):
            self.print_prod(i, p, "prod", cp[i]/(cp[i]+cg[i]+cr[i]), 
                            cg[i]/(cp[i]+cg[i]+cr[i]))
        self.print_prod(0, self.generic, "generic", 0, 0)

    def print_prod(self, i, p, pr, cpi, cgi):
        ps = p+self.alpha
        norm = np.sum(ps)
        top_k = np.argsort(-ps)[:20]
        print
        print pr,i, cpi, cgi
        for t in top_k:
            print self.all_words[t], ps[t]/float(norm)


    


if __name__=='__main__':
    pass
    