use strict;
use warnings;
use JSON::PP;
use IPC::Open3;
use Symbol qw(gensym);

open my $fh, '<', '/home/joshua/homeWizard/HomeWizard API.postman_collection.json' or die "Cannot read collection\n";
my $collection = decode_json(do { local $/; <$fh> });
my %vars = map { $_->{key} => $_->{value} } @{$collection->{variable}};
die "Invalid gateway address\n" unless $vars{ip_address} =~ /\A[\w.:-]+\z/;
my $password = $vars{password};
$password =~ s/([^A-Za-z0-9_.~-])/sprintf("%%%02X", ord($1))/ge;
my $base = "http://$vars{ip_address}/$password";

sub shape {
    my ($v, $depth) = @_;
    return 'null' unless defined $v;
    return 'boolean' if JSON::PP::is_bool($v);
    return 'scalar' unless ref $v;
    return ref($v) if $depth > 6;
    if (ref($v) eq 'HASH') {
        return { map { $_ => shape($v->{$_}, $depth + 1) } sort keys %$v };
    }
    if (ref($v) eq 'ARRAY') {
        return { count => scalar(@$v), sample_shape => @$v ? shape($v->[0], $depth + 1) : undef };
    }
    return 'other';
}

my @routes = qw(/get-sensors /handshake);
my @results;
$| = 1;
for my $route (@routes) {
    my $err = gensym;
    my $pid = open3(my $in, my $out, $err, 'curl', '--config', '-');
    my $url = $route eq '/handshake' ? "http://$vars{ip_address}$route" : "$base$route";
    print $in qq(url = "$url"\nsilent\nconnect-timeout = 3\nmax-time = 10\nmax-filesize = 2097152\nnoproxy = "*"\nwrite-out = "\\n%{http_code}"\n);
    close $in;
    my $raw = do { local $/; <$out> } // '';
    my $error = do { local $/; <$err> } // '';
    waitpid($pid, 0);
    my $exit = $? >> 8;
    my ($body, $status) = $raw =~ /\A(.*)\n(\d{3})\z/s;
    my $result = { route => $route, curl_exit => $exit, http_status => $status // '000' };
    $result->{authentication} = $route eq '/handshake' ? 'none' : 'password prefix';
    if (!$exit && defined $body) {
        my $json = eval { decode_json($body) };
        $result->{json} = $@ ? JSON::PP::false : JSON::PP::true;
        if (!$@) {
            $result->{shape} = shape($json, 0);
            if ($route eq '/get-sensors' && ref($json->{response}{kakusensors}) eq 'ARRAY') {
                my $id = $json->{response}{kakusensors}[0]{id};
                push @routes, "/kks/get/$id/log" if defined($id) && $id =~ /\A[0-9]+\z/;
                my %types;
                $types{$_->{type}}++ for @{$json->{response}{switches} // []};
                $result->{switch_types} = \%types;
            }
            # Only report a small, non-sensitive status vocabulary; never response values.
            if (ref($json) eq 'HASH' && defined($json->{status}) && !ref($json->{status}) && $json->{status} =~ /\A(?:ok|success|error|failed)\z/i) {
                $result->{api_status} = $json->{status};
            }
        }
        $result->{body_bytes} = length($body);
    }
    push @results, $result;
    print JSON::PP->new->canonical->encode($result), "\n";
}
open my $report, '>', '/tmp/homewizard-route-extra-results.json' or die "Cannot save summary\n";
print $report JSON::PP->new->canonical->pretty->encode(\@results);
