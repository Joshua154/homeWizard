use strict;
use warnings;
use JSON::PP;
use IPC::Open3;
use Symbol qw(gensym);

# Explicit read-only routes. Raw bodies and credentials never touch disk/output.
open my $fh, '<', 'HomeWizard API.postman_collection.json' or die "Missing local collection\n";
my $collection = decode_json(do { local $/; <$fh> });
my %vars = map { $_->{key} => $_->{value} } @{$collection->{variable}};
die "Invalid address\n" unless $vars{ip_address} =~ /\A[\w.:-]+\z/;
my $password = $vars{password};
$password =~ s/([^A-Za-z0-9_.~-])/sprintf("%%%02X", ord($1))/ge;
my $full_inventory;
for my $route (qw(handshake get-sensors get-status swlist gplist)) {
    my $url = "http://$vars{ip_address}/" . ($route eq 'handshake' ? '' : "$password/") . $route;
    my $pid = open3(my $in, my $out, my $err = gensym, 'curl', '--config', '-');
    print $in qq(url = "$url"\nsilent\nconnect-timeout = 3\nmax-time = 10\nmax-filesize = 2097152\nnoproxy = "*"\n);
    close $in;
    my $raw = do { local $/; <$out> } // '';
    my $errors = do { local $/; <$err> };
    waitpid($pid, 0);
    die "Read failed: $route\n" if $?;
    my $json = eval { decode_json($raw) };
    die "Invalid response: $route\n" if $@ || $json->{status} ne 'ok';
    my $response;
    $full_inventory = $json->{response} if $route eq 'get-sensors';
    if ($route eq 'swlist' || $route eq 'gplist') {
        my $category = $route eq 'swlist' ? 'switches' : 'scenes';
        my $encoder = JSON::PP->new->canonical;
        print "$route complete records equal inventory: ",
            $encoder->encode($json->{response}) eq $encoder->encode($full_inventory->{$category}) ? "yes\n" : "no\n";
    }
    if ($route eq 'handshake') {
        $response = {serial => 'TEST-GATEWAY-001', version => $json->{response}{version}};
    } else {
        my $source = $json->{response};
        $source = {$route eq 'swlist' ? 'switches' : 'scenes' => $source} if ref($source) eq 'ARRAY';
        my %safe;
        for my $category (qw(switches kakusensors thermometers rainmeters windmeters weatherdisplays scenes energylinks energymeters heatlinks hues uvmeters)) {
            next unless ref($source->{$category}) eq 'ARRAY';
            my @records;
            for my $record (@{$source->{$category}}) {
                my %clean;
                for my $key (qw(id type status te hu lowBattery tte)) {
                    next unless exists $record->{$key};
                    my $value = $record->{$key};
                    next if ref($value) && !JSON::PP::is_bool($value);
                    # Only numeric readings and short API enum tokens.
                    next if defined($value) && $value !~ /\A(?:-?\d+(?:\.\d+)?|[a-zA-Z_]{1,24})\z/;
                    $clean{$key} = $value;
                }
                $clean{name} = "$category $clean{id}" if exists $record->{name};
                push @records, \%clean;
            }
            $safe{$category} = \@records;
        }
        $response = ref($json->{response}) eq 'ARRAY' ? $safe{$route eq 'swlist' ? 'switches' : 'scenes'} : \%safe;
        # Field names only to help identify missing, safe measurement mappings.
        my %keys;
        for my $cat (keys %$source) {
            next if $cat eq 'cameras' || ref($source->{$cat}) ne 'ARRAY';
            $keys{$cat}{$_} = 1 for map { keys %$_ } @{$source->{$cat}};
        }
        print "$route fields: ", encode_json({map { $_ => [sort keys %{$keys{$_}}] } keys %keys}), "\n";
    }
    open my $dest, '>', "tests/fixtures/$route.json" or die "Cannot write fixture\n";
    print $dest JSON::PP->new->canonical->pretty->encode({status => 'ok', version => $json->{version}, response => $response});
    print "Saved sanitized $route fixture\n";
}
