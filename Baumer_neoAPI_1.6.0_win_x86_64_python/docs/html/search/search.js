var searchResultsText=["Sorry, no documents matching your query.","Found <b>1</b> document matching your query.","Found <b>$num</b> documents matching your query."];
var serverUrl="file://C:/SL/DOC TOOLS/SLP DOCOUT/searchengine.html";
var tagMap = {
};

function SearchBox(name, resultsPath, inFrame, label)
{
  this.searchLabel = label;
  this.DOMSearchField = function()
  {  return document.getElementById("MSearchField");  }
  this.DOMSearchBox = function()
  {  return document.getElementById("MSearchBox");  }
  this.OnSearchFieldFocus = function(isActive)
  {
    if (isActive)
    {
      this.DOMSearchBox().className = 'MSearchBoxActive';
      var searchField = this.DOMSearchField();
      if (searchField.value == this.searchLabel)
      {
        searchField.value = '';
      }
    }
    else
    {
      this.DOMSearchBox().className = 'MSearchBoxInactive';
      this.DOMSearchField().value   = this.searchLabel;
    }
  }
}

function trim(s) {
  return s?s.replace(/^\s\s*/, '').replace(/\s\s*$/, ''):'';
}

function getURLParameter(name) {
  return decodeURIComponent((new RegExp('[?|&]'+name+
         '='+'([^&;]+?)(&|#|;|$)').exec(location.search)
         ||[,""])[1].replace(/\+/g, '%20'))||null;
}

var entityMap = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': '&quot;',
  "'": '&#39;',
  "/": '&#x2F;'
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"'\/]/g, function (s) {
    return entityMap[s];
  });
}

function UcFirst(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

function searchFor(query,page,count) {
    if(trim(query).length<3)
    {
        var results = $('#searchresults');
        results.html('<p>Query too short (3 chars mininum).</p>');
        return;
    }

    var xmlData=document.getElementById('searchdata').innerHTML;
    if(xmlData.indexOf("<add>")<0)
    {
        alert("Append <script id=\"searchdata\" type=\"text/xmldata\"> to the content of search.html, then the content of searchdata.xml, and end by </script>.\n\nsearchdata.xml is generated when SEARCHENGINE, SERVER_BASED_SEARCH and EXTERNAL_SEARCH options are enabled.");
        return;
    }
    xmlData=xmlData.substring(xmlData.indexOf("<add>"),xmlData.indexOf("</add>")+6);

    var xmlParser=new DOMParser().parseFromString(xmlData,"text/xml");

    count=0;
    output = '';
    output_last = '';
    output_last2 = '';
    var doc=xmlParser.getElementsByTagName("doc");
    for (i=0;i<doc.length;i++)
    {
        var type = '';
        var name = '';
        var url = '';
        var text = '';
        var tmp = doc[i].getElementsByTagName("field")

        for (var x = 0; x < tmp.length; x++) {
            
            if (tmp[x].getAttribute('name') == 'type')
                type = tmp[x].childNodes[0].nodeValue;
            if (tmp[x].getAttribute('name') == 'name' && tmp[x].childNodes[0])
                name = tmp[x].childNodes[0].nodeValue;
            if (tmp[x].getAttribute('name') == 'url' && tmp[x].childNodes[0])
                url = tmp[x].childNodes[0].nodeValue;
            if (tmp[x].getAttribute('name') == 'text' && tmp[x].childNodes[0])
                text += tmp[x].childNodes[0].nodeValue;
            if (tmp[x].getAttribute('name') == 'keywords' && tmp[x].childNodes[0])
                text += ' ' + tmp[x].childNodes[0].nodeValue;
        }

        if (text.toLowerCase().indexOf(query.toLowerCase()) >= 0)
        {
            count++;

            if ((type != "page") && (type != "source") )
            {
                output += '<tr class="searchresult active">';
                output += '<td align="right"></td>';
                output += '<td>' + escapeHtml(UcFirst(type)) + ':&#160; ';
                output += '<a href="' + escapeHtml(url) + '">';
                output += escapeHtml(name);
                output += '</a>';
                output += '</td>';

                var start = text.toLowerCase().indexOf(query.toLowerCase());
                var fragmentcount = 0;
                while (start >= 0 && fragmentcount < 3) {
                    quotestart = Math.max(start - 30, 0);
                    quoteend = Math.min(start + query.length + 30, text.length);
                    fragment = '';
                    if (quotestart > 0)
                        fragment += '...';
                    fragment += escapeHtml(text.substring(quotestart, start));
                    fragment += '<span class="hl">';
                    fragment += escapeHtml(text.substring(start, start + query.length));
                    fragment += '</span>';
                    fragment += escapeHtml(text.substring(start + query.length, quoteend));
                    if (quoteend < query.length);
                    fragment += '...';
                    output += '<tr><td></td><td>' + fragment + '</td></tr>';

                    start = text.toLowerCase().indexOf(query.toLowerCase(), start + 1);
                    fragmentcount++;
                }

                output += "</tr>";
            }
            else if(type == "page")
            {
                output_last += '<tr class="searchresult active">';
                output_last += '<td align="right"></td>';
                output_last += '<td>' + escapeHtml(UcFirst(type)) + ':&#160;';
                output_last += '<a href="' + escapeHtml(url) + '">';
                output_last += escapeHtml(name);
                output_last += '</a>';
                output_last += '</td>';

                var start = text.toLowerCase().indexOf(query.toLowerCase());
                var fragmentcount = 0;
                while (start >= 0 && fragmentcount < 3) {
                    quotestart = Math.max(start - 30, 0);
                    quoteend = Math.min(start + query.length + 30, text.length);
                    fragment = '';
                    if (quotestart > 0)
                        fragment += '...';
                    fragment += escapeHtml(text.substring(quotestart, start));
                    fragment += '<span class="hl">';
                    fragment += escapeHtml(text.substring(start, start + query.length));
                    fragment += '</span>';
                    fragment += escapeHtml(text.substring(start + query.length, quoteend));
                    if (quoteend < query.length);
                    fragment += '...';
                    output_last += '<tr><td></td><td>' + fragment + '</td></tr>';

                    start = text.toLowerCase().indexOf(query.toLowerCase(), start + 1);
                    fragmentcount++;
                }

                output_last += "</tr>";
            }
            else
            {
                output_last2 += '<tr class="searchresult active">';
                output_last2 += '<td align="right"></td>';
                output_last2 += '<td>' + escapeHtml(UcFirst(type)) + ':&#160;';
                output_last2 += '<a href="' + escapeHtml(url) + '">';
                output_last2 += escapeHtml(name);
                output_last2 += '</a>';
                output_last2 += '</td>';

                var start = text.toLowerCase().indexOf(query.toLowerCase());
                var fragmentcount = 0;
                while (start >= 0 && fragmentcount < 3) {
                    quotestart = Math.max(start - 30, 0);
                    quoteend = Math.min(start + query.length + 30, text.length);
                    fragment = '';
                    if (quotestart > 0)
                        fragment += '...';
                    fragment += escapeHtml(text.substring(quotestart, start));
                    fragment += '<span class="hl">';
                    fragment += escapeHtml(text.substring(start, start + query.length));
                    fragment += '</span>';
                    fragment += escapeHtml(text.substring(start + query.length, quoteend));
                    if (quoteend < query.length);
                    fragment += '...';
                    output_last2 += '<tr><td></td><td>' + fragment + '</td></tr>';

                    start = text.toLowerCase().indexOf(query.toLowerCase(), start + 1);
                    fragmentcount++;
                }

                output_last2 += "</tr>";
            }
        }
    }

    var html_open = '<div class="container"><div class="row"><div class="col-sm-12 panel" style="padding-bottom: 15px;">';
    var html_close = '</div></div></div>';

    output = html_open + '<table class="directory table table-striped">' + output + output_last + output_last2 + '</table>' + html_close;

    var results = $('#content');
    
    if (count == 0) {
        results.append(html_open + '<p>' + searchResultsText[0] + '</p>' + html_close);
    } else if (count==1) {
        results.append(html_open + '<p>' + searchResultsText[1] + '</p>' + html_close);
    } else {
        results.append(html_open + '<p>' + searchResultsText[2].replace(/\$num/, count) + '</p>' + html_close);
    }
    results.append(output);
}

$(document).ready(function() {
    var query = trim(getURLParameter('query'));

    // only if on the search page... hide some stuff
    if ($(location).attr('href').indexOf('search.html') > 0 )
    {
        $('#content > .container').css('visibility', 'hidden').css('display', 'none');
        tmp = $('.headertitle').parent().html();
        $('.headertitle').parent().html('');
        $('#content').append('<div class="container">' + tmp + '</div>');
        
    }

  if (query) {
      searchFor(query, 0, 20);
  } else {
    var results = $('#results');
      results.html('<p>Sorry, no documents matching your query.</p>');
  }
});
