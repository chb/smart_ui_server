/*
 * JMVC Controller for the SMArt bootstrap
 *
 * Ben Adida (ben.adida@childrens.harvard.edu)
 * Arjun Sanyal (arjun.sanyal@childrens.harvard.edu)
 * Josh Mandel (joshua.mandel@childrens.harvard.edu)
 */

SMART_HELPER  = {};

SMART_HELPER.apps_by_activity = {};
SMART_HELPER.tokens_by_app = {};
SMART_HELPER.creds_and_info_generator = function(app, callback) { 
    callback( {'credentials' : 'foobar',
     	    'record_info' : {
		'full_name' : RecordController.CURRENT_RECORD.label,
		'id' : RecordController.CURRENT_RECORD.record_id
	    }
	});
};


//todo: this fn should take app_emai, for per-call token management
SMART_HELPER.api = function(activity, message, callback) {
	var app_id = SMART_HELPER.apps_by_activity[activity.uuid];
    var app = jQuery.grep(PHAController.phas, function(pha) {return (pha.id === app_id);})[0];

    var os = new OAuthServiceSmart(
                  {consumer_key: app.data.consumer_key, 
                   consumer_secret: app.data.secret, 
                   token_key: SMART_HELPER.tokens_by_app[app.id].token, 
                   token_secret: SMART_HELPER.tokens_by_app[app.id].secret, });

    var request = os.getSignedRequest({method: message.method,
				       url: SMART_API_SERVER+message.func,
				       query:message.params,
				       contentType: message.contentType
	});
    
    	$.ajax({
		beforeSend: function(xhr) {
		    var request_headers = request.getRequestHeaders();
		    for (var header in request_headers) {
			xhr.setRequestHeader(header, request_headers[header]);
		    }},
		    dataType: "text",
		    url: SMART_API_SERVER+message.func,
//		    contentType: message.contentType, //  todo: THIS BREAKS THINGS (better in jQuery 1.4?) -JM 
		    data: message.params,
		    type: request.getMethod(),
			success: callback,
			error: function(data) {
			    	  alert("error");
			      }
	});
};

SMART_HELPER.resume_activity = function(activity, callback) {
	MainController.dispatch('make_visible', $(activity.iframe));
	callback();
};

SMART_HELPER.start_activity = function(activity, callback) {
    	var account_id_enc = encodeURIComponent(ACCOUNT.account_id);
    	var record_id_enc = encodeURIComponent(RecordController.CURRENT_RECORD.record_id);
    	
    	var get_tokens = function() {
        	var app_email_enc = encodeURIComponent(resolved_activity.app);
        	SMART_HELPER.apps_by_activity[activity.uuid] = resolved_activity.app;
        	$.ajax({
              		url: "/smart_api/accounts/"+account_id_enc+"/apps/"+app_email_enc+"/records/"+record_id_enc+"/launch",
    			data: null,
    			type: "GET",
    			dataType: "text",
    			success: 
    			      function(data) {
        				d  = MVC.Tree.parseXML(data);    		   
        				if (d.AccessToken.App["@id"] !== resolved_activity.app)
        					throw "Got back access tokens for a different app! " + resolved_activity.app +  " vs. " + d.AccessToken.App["@id"];
        				SMART_HELPER.tokens_by_app[resolved_activity.app] = {token:d.AccessToken.Token, secret: d.AccessToken.Secret};
        				
        				 var interpolation_args = {
        			    		  'record_id' : RecordController.RECORD_ID,
        			    		  'account_id' : ACCOUNT_ID
        			    		  };

        			  	  startURL = interpolate_url_template(resolved_activity.url, interpolation_args);
        			  	  RecordController.APP_ID = resolved_activity.app;
        			  	  var frame_id = "app_content_iframe_"+randomUUID();
        			  	  $('#main_canvas').append('<iframe src="'+startURL+'" class="activity_iframe" id="'+frame_id+'" width="90%" height="90%"> </iframe>');
        			  	  var frame = $("#"+frame_id);
        			  	  $(window).resize();
        				  MainController.dispatch('make_visible', frame);
        				  
        				  callback( frame[0]);
    			      },
    			error: function(data) {
    			    	  // error handler
    			    	  err = data;
    			    	  alert("error fetching token xml " + data);
    			      }
        	});    		
    	}
    	
    	var resolved_activity= new Activity(activity.name, activity.app, get_tokens);
};



MainController = MVC.Controller.extend('main', {
  load: function(params) {      
      ACCOUNT = new Account(ACCOUNT_ID); // init the account via model
      SMART = new SMART_CONTAINER(SMART_HELPER);
      this.setup();
  },

  make_visible: function(element) {
		$(".activity_iframe:visible").each(function(pos, f) {
 			  f = $(f);
 			  f.hide();
 		  }
 	    );
		
	    $("#app_content").hide();
	    $("#app_content_iframe").hide();

	    element.show();
	    element.css("border", "0px");

 	   
 		$(window).resize();

  },
  
  setup: function(params) {
    RecordController.dispatch('setup');
	PHAController.dispatch('setup');
    PatientSearchController.dispatch('index');

    var scrollbarWidth = function() {
	var div = $('<div style="width:50px;height:50px;overflow:hidden;position:absolute;top:-200px;left:-200px;"><div style="height:100px;"></div>');
	// Append our div, do our calculation and then remove it
	$('body').append(div);
	var w1 = $('div', div).innerWidth();
	div.css('overflow-y', 'scroll');
	var w2 = $('div', div).innerWidth();
	$(div).remove();
	return (w1 - w2);
    }();
    
    $(window).resize(function() {
    	var $elt =$(".activity_iframe:visible");
    	
    	if ($elt.length == 0)
    		$elt = $("#app_content");

    	$(".activity_iframe").each(function(pos,f) {
 	  			  f = $(f);
 	  			  f.hide();
 	  	    });
    	
    	$(".activity_iframe").each(function(pos, f) {
 			  f = $(f);
	  			  f.css("height",$("#bigbody").height()- $("#footer").height()-$('#header').height());
	  			  f.css("width", $("#bigbody").width()-$('#app_selector').width());
 	    });
 	    
		    $("#app_content").css("height",$("#bigbody").height()- $("#footer").height()-$('#header').height());
	    $("#app_content").css("width", $("#bigbody").width()-$('#app_selector').width()); 

        $elt.show();    		
    });
    
    $(window).resize();

 

    $.address.change(function(event) {
    	if (event.value === "manage_apps")
    	{
    		PHAController.dispatch('index');
    	}
    	else if (event.value === "_patient_search_tab_panel_hidden")	
    	{
    		PatientSearchController.dispatch('index');
    	}
    	else if (event.value.match(/^app\//))	
    	{
    		PHAController.dispatch('hash_change', event);
    	}

    });

    
  },
  

});