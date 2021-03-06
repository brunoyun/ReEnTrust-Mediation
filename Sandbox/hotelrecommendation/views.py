from django.shortcuts import render
from decimal import *
from django.shortcuts import redirect
from django.views import View
from .forms import UserForm
from .forms import FeedbackForm
from .forms import LogForm
from .models import User
from .models import Hotel
from .models import LogInstance
from django.db.models import Func, F
from .models import LogComment
from .models import LogAction
from .models import Rating
from .models import CacheRecommendation
from .models import CacheClosest
import pickle
from sklearn.neighbors import NearestNeighbors
import math


#We fit the recommender system
top_results=10
#0 for filtering and 1 for euclidian
closest_user_function= 1

max_user_rating = Rating.objects.all().order_by('rating_note').last().rating_note
min_user_rating = Rating.objects.all().order_by('rating_note').first().rating_note

def averageNote(hotel):
    list_ratings = list(Rating.objects.filter(rating_hotel = hotel))
    result = 0
    for r in list_ratings:
        result+= r.rating_note
    result /= len(list_ratings)
    result = (result - min_user_rating) / (max_user_rating- min_user_rating) * 5
    return result

def recommandation(algo, data, user_id):

    description = str(algo)+"+"+str(data)
    corresponding_user = User.objects.filter(id=user_id)[0]
    db_cache_rec = CacheRecommendation.objects.filter(cache_user = corresponding_user, cache_description= description)

    if not db_cache_rec:
        result = []
        if algo == 1:
            pickle_off_1=open("pickle/Rec1.pickle","rb")
            my_recommender1 = pickle.load(pickle_off_1)
            result= my_recommender1[data].predict([user_id]).values.tolist()
        elif algo == 2:
            pickle_off_2=open("pickle/Rec2.pickle","rb")
            my_recommender2 = pickle.load(pickle_off_2)
            result= my_recommender2[data].predict([user_id]).values.tolist()
        else:
            pickle_off_3=open("pickle/Rec3.pickle","rb")
            my_recommender3 = pickle.load(pickle_off_3)
            result= my_recommender3[data].predict([user_id]).values.tolist()
        CacheRecommendation(cache_user = corresponding_user, cache_description = description, cache_recommendation_hotel= result).save()
        return result
    else:
        converted = CacheRecommendation.objects.filter(cache_user = corresponding_user, cache_description = description)[0].cache_recommendation_hotel[1:-1].split("], [")
        result = []
        for l in converted:
            result.append([int(l.split(',')[0].replace('[', '')[1:-1])])

        return result




class IndexView(View):

    def get(self,request):
        context = {}
        return render(request, 'hotelrecommendation/index.html', context)

    def post(self,request):

        form = LogForm(data = request.POST)
        if form.is_valid():
            dataInstance = form.cleaned_data.get('dataInstance')
        print(form.errors)


        #We create a new instance
        newLogInstance = LogInstance(log_identification_string=dataInstance)
        newLogInstance.save()

        #We create a logAction that the user has logged In
        newLogAction = LogAction(log_instance_id= newLogInstance.id, log_action_description="User has logged in, with the following identification code:"+dataInstance)
        newLogAction.save()
        return redirect('hotelrecommendation:result_view', newLogInstance.id, 18, 200, False,False,False,"M",1, "L", 0)

class ResultView(View):

    def get(self, request,log, age, target_price,physically_disabled,is_married,have_kids,gender, algo,type, data):

        #We create a logAction that the page was shown to the user
        newLogAction = LogAction(log_instance_id= log, log_action_description="User is shown the page (age,price,wheelchair,married,kids,gender,algo,type,data) = ("+str(age)+","+str(target_price)+","+str(physically_disabled)+","+str(is_married)+","+str(have_kids)+","+gender+","+str(algo)+","+str(type)+","+str(data)+").")
        newLogAction.save()

        #We get the comments from the user
        set_comments = {}
        for c in LogComment.objects.filter(log_instance_id = log):
            set_comments[c.log_about] = { 'log_radio1' : c.log_radio1,
                                          'log_comment' : c.log_comment,}

        #We have to find old instances of this user
        OldActionsUpdate = [s for s in list(LogAction.objects.filter(log_instance_id=log)) if "User requested the page (age,price,wheelchair,married,kids,gender,algo,type,data)" in s.log_action_description]
        OldPresetsString = [s.log_action_description[85:-2] for s in OldActionsUpdate]
        OldPresets = []
        for s in OldPresetsString:
            splitted = s.split(',')
            OldPresets.append({
                'age' : int(splitted[0]),
                'price': Decimal(splitted[1]),
                'wheelchair': splitted[2] == "True",
                'married': splitted[3] == "True",
                'kids': splitted[4] == "True",
                'gender': splitted[5],
                'algo': int(splitted[6]),
                'type': splitted[7],
                'data': int(splitted[8]),
            })

        OldPresets = OldPresets[-4:]

        #We get the users with the same status
        set_relevant_users = []
        similarUsers = []
        set_closest = []


        if closest_user_function == 1:
            for o in OldPresets:
                description = str(o['age'])+"+"+str(o['price'])+"+"+str(o['wheelchair'])+"+"+str(o['married'])+"+"+str(o['kids'])+"+"+str(o['gender'])+"+"+str(o['type'])
                db_closest = CacheClosest.objects.filter(cache_description = description)

                if db_closest:
                    closest_neigh_db = db_closest[0].cache_user
                    set_relevant_users.append(closest_neigh_db)
                else:
                    closest_neigh_db = compute_neighbor(o['age'],o['price'],o['wheelchair'],o['married'],o['kids'],o['gender'],o['type'])
                    CacheClosest(cache_user = closest_neigh_db, cache_description= description, cache_method= 1).save()
                    set_relevant_users.append(closest_neigh_db)


            if set_relevant_users:
                similarUsers.append(set_relevant_users[-1])

            set_closest = set_relevant_users
        else:
            for o in OldPresets:
                amplitude = 0
                while True:
                    relevant_users = User.objects.filter(type = o['type'],user_disable = o['wheelchair'], user_is_married = o['married'], user_have_kids = o['kids'], gender= o['gender'], user_target_price__gte = o['price']-amplitude, user_target_price__lte = o['price']+amplitude)
                    if not relevant_users:
                        amplitude=amplitude+10
                    else:
                        set_relevant_users.append(relevant_users)
                        break

            set_ordered_age = []
            #We have to rank them and take the closest user and the similar users
            for s in set_relevant_users:
                set_ordered_age.append(s.annotate(age_diff=Func(F('user_age') - age, function='ABS')).order_by('age_diff'))

            if set_ordered_age:
                similarUsers = (list(set_ordered_age[-1][:5]))

            for s in set_ordered_age:
                set_closest.append(s.last())


        #We take the predictions for the closest user
        set_predictions = []
        for o,s in zip(OldPresets,set_closest):
            set_predictions.append(recommandation(o['algo'],o['data'],s.id))


        #We take the hotels that correspond
        set_list_hotels = []
        for s in set_predictions:
            listHotelT = []
            for l in s:
                listHotelT.append(Hotel.objects.get(id = l[0]))
            set_list_hotels.append(listHotelT)
        #We take the scores that correspond
        set_list_averageScore = []
        for l in set_list_hotels:
            listScore = []
            for z in l:
                listScore.append(averageNote(z))
            set_list_averageScore.append(listScore)
        #We merge them together
        set_list_hotel_score = []
        for l,z in zip(set_list_hotels,set_list_averageScore):
            set_list_hotel_score.append(zip(l,z))

        #We take statistics on those hotels
        set_averagePrice = []
        set_averageReview = []
        set_percentageSingle = []
        set_percentageTwin = []
        set_percentageFamily = []
        set_percentageDouble = []
        set_percentageSwim = []
        set_percentageBreak = []
        set_percentageAccessible = []
        set_percentageMicheling = []

        for Q in set_list_hotels:
            averagePrice = 0
            averageReview = 0
            percentageSingle = 0
            percentageTwin = 0
            percentageFamily = 0
            percentageDouble = 0
            percentageSwim = 0
            percentageBreak = 0
            percentageMichelin =0
            percentageAccessible = 0

            for l in Q:
                averagePrice += l.hotel_night_price
                averageReview +=l.hotel_user_reviews
                if l.hotel_room_type == "S":
                    percentageSingle = percentageSingle+1
                elif l.hotel_room_type == "T":
                    percentageTwin = percentageTwin+1
                elif l.hotel_room_type == "F":
                    percentageFamily = percentageFamily+1
                else:
                    percentageDouble = percentageDouble+1

                if l.hotel_disability_access:
                    percentageAccessible = percentageAccessible +1

                if l.hotel_swimming_pool:
                    percentageSwim = percentageSwim +1

                if l.hotel_breakfast_available:
                    percentageBreak = percentageBreak +1

                if l.hotel_michelin_restaurant:
                    percentageMichelin = percentageMichelin +1

            percentageAccessible /= (top_results/100)
            set_percentageAccessible.append(percentageAccessible)

            percentageMichelin /= (top_results/100)
            set_percentageMicheling.append(percentageMichelin)

            percentageSingle /= (top_results/100)
            set_percentageSingle.append(percentageSingle)

            percentageTwin /= (top_results/100)
            set_percentageTwin.append(percentageTwin)

            percentageFamily /= (top_results/100)
            set_percentageFamily.append(percentageFamily)

            percentageDouble /= (top_results/100)
            set_percentageDouble.append(percentageDouble)

            percentageSwim /= (top_results/100)
            set_percentageSwim.append(percentageSwim)

            percentageBreak /= (top_results/100)
            set_percentageBreak.append(percentageBreak)

            averagePrice /= top_results
            set_averagePrice.append(averagePrice)

            averageReview /= top_results
            set_averageReview.append(averageReview)


        context ={
            'target_price': target_price,
            'physically_disabled': physically_disabled,
            'is_married': is_married,
            'have_kids': have_kids,
            'age' : age,
            'log' : log,
            'gender': gender,
            "L" : zip(set_list_hotel_score,OldPresets,set_averagePrice, set_averageReview ,set_percentageSingle ,set_percentageTwin ,set_percentageFamily ,set_percentageDouble ,set_percentageSwim ,set_percentageBreak ,set_percentageAccessible,set_percentageMicheling),
            'S' : similarUsers,
            'algo' : algo,
            'set_comments' : set_comments,
            'type' : type,
            'data' : data,
                  }

        return render(request, 'hotelrecommendation/results.html', context)


    def post(self, request, log, age, target_price, physically_disabled, is_married, have_kids, gender, algo,type, data):

        if request.POST.__contains__('comment'): #This means that we are saving a comment
            form = FeedbackForm(data = request.POST)
            feed = '0'
            comment = ''
            instance = request.POST.__getitem__('data-instance')
            if form.is_valid():
                feed = form.cleaned_data.get('feed')
                comment = form.cleaned_data.get('comment')
            print(form.errors)

            feed = 'No answers' if feed == "" else 'Totally disagree' if feed == "1" else 'Disagree' if feed == "2" else 'Neutral' if feed == "3" else 'I do not know' if feed == "4" else 'Agree' if feed == "5" else 'Totally Agree'

            if not LogComment.objects.filter(log_instance_id = log, log_about= instance).exists(): #We never saw such object
                newLogComment = LogComment(log_instance_id = log, log_comment = comment, log_radio1 = feed, log_about= instance)
                newLogComment.save()

                #We save the action of giving a feedback
                newLogAction = LogAction(log_instance_id= log, log_action_description="User gave his feedback for "+instance+".")
                newLogAction.save()
            else: #We have such objects, in this case, we update the database
                LogComment.objects.filter(log_instance_id = log, log_about= instance).update(log_comment = comment, log_radio1 = feed)

                #We save the action of updating a feedback
                newLogAction = LogAction(log_instance_id= log, log_action_description="User updated his feedback for "+instance+".")
                newLogAction.save()

        elif request.POST.__contains__('algo'): #This means that we are changing a profile
            form = UserForm(data = request.POST)

            status_gender = request.POST.__getitem__('enabled-gender')
            status_purpose = request.POST.__getitem__('enabled-purpose')
            status_age = request.POST.__getitem__('enabled-age')
            status_wheelchair = request.POST.__getitem__('enabled-wheelchair')
            status_partner = request.POST.__getitem__('enabled-partner')
            status_kids = request.POST.__getitem__('enabled-kids')
            status_price = request.POST.__getitem__('enabled-price')

            if form.is_valid():
                age = form.cleaned_data.get('age')
                target_price = form.cleaned_data.get('target_price')
                physically_disabled = form.cleaned_data.get('physically_disabled')
                is_married = form.cleaned_data.get('is_married')
                have_kids = form.cleaned_data.get('have_kids')
                gender = form.cleaned_data.get('gender')
                algo =  form.cleaned_data.get('algo')
                type = form.cleaned_data.get('type')
                data = form.cleaned_data.get('data')
            print(form.errors)

            #We create a logAction that the page was shown to the user
            newLogAction = LogAction(log_instance_id= log, log_action_description="User requested the page (age,price,wheelchair,married,kids,gender,algo,type,data) = ("+str(age)+","+str(target_price)+","+str(physically_disabled)+","+str(is_married)+","+str(have_kids)+","+gender+","+str(algo)+","+str(type)+","+str(data)+").")
            newLogAction.save()

        return redirect('hotelrecommendation:result_view', log, age, target_price, physically_disabled,is_married,have_kids,gender,algo, type, data)



class ResultRatingUser(View):
    def get(self, request, log, age, target_price,physically_disabled,is_married,have_kids,gender,algo, id_user, type, data):



        #We need to display the ratings from a specific user
        rater = User.objects.filter(id = id_user).first()

        #We need to get the hotels that he rated
        rater_rating = Rating.objects.filter(rating_user = id_user, rating_type = data)
        rater_rating = list(rater_rating)

        #We create a logAction that the page was shown to the user
        newLogAction = LogAction(log_instance_id= log, log_action_description="We show the page of user "+str(rater.id)+".")
        newLogAction.save()

        context ={
            'log' : log,
            'target_price': target_price,
            'physically_disabled': physically_disabled,
            'is_married': is_married,
            'have_kids': have_kids,
            'age' : age,
            'algo': algo,
            'gender': gender,
            'rater' : rater,
            'rater_rating': rater_rating,
            'type' : type,
            'data' : data,
                  }

        return render(request, 'hotelrecommendation/rating_detail.html', context)







##### MISC FUNCTIONS


def int_bool(val):
    if val:
        return 1
    return 0

def int_gen(val):
    if val=='M':
        return 0
    return 1

def int_type(val):
    if val=='B':
        return 0
    return 1

def user_to_user_sample(u):
    return (u.user_age,float(u.user_target_price),int_bool(u.user_disable),int_bool(u.user_is_married),int_bool(u.user_have_kids),int_gen(u.gender),int_type(u.type))

def dist(a,b):
    # a and b are two users with the following (numerical) parameters: age, target_price, physically_disabled, is_married, have_kids, gender, type

    # weights on the parameters:
    # age -> 1.5/7
    # target_price -> 0.5/7
    # physically disables -> 2/7
    # is_married -> 0.25/7
    # have_kids -> 0.5/7
    # gender -> 2/7
    # type -> 0.25/7

    # weights array:
    weights = [200,1,100000000,100000000,100000000,100000000,100000000]

    #euclidean distance:
    d = math.sqrt(weights[0]*((a[0]-b[0])**2)+weights[1]*((a[1]-b[1])**2)+weights[2]*((a[2]-b[2])**2)+weights[3]*((a[3]-b[3])**2)+weights[4]*((a[4]-b[4])**2)+weights[5]*((a[5]-b[5])**2)+weights[6]*((a[6]-b[6])**2))

    return d




def compute_neighbor(age,target_price,physically_disabled,is_married,have_kids,gender,type):
    target_user=[age,float(target_price),int_bool(physically_disabled),int_bool(is_married),int_bool(have_kids),int_gen(gender),int_type(type)]
    samples=[]
    tmp=()
    dic_users={}
    for u in User.objects.all():
        tmp=user_to_user_sample(u)
        samples.append(tmp)
        dic_users[u.id]=tmp

    rev_dic_users={value: key for key,value in dic_users.items()}

    neigh = NearestNeighbors(n_neighbors=2, algorithm='ball_tree',metric=dist)
    neigh.fit(samples)

    kNeighb = neigh.kneighbors([target_user], 5, return_distance=False)

    nn_id = rev_dic_users[samples[kNeighb[0][0]]]
    nn = User.objects.filter(id = nn_id).first()

    return nn





